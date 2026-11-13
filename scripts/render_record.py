#!/usr/bin/env python3
"""Render a verified project release snapshot as native Feishu table XML."""

import argparse
from datetime import date, datetime
import json
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


OVERVIEW_HEADERS = ("技能名称", "仓库地址", "当前版本", "分支说明")
RELEASE_HEADERS = (
    "技能名称", "修复日期", "问题版本", "问题描述", "原因分析",
    "解决方案", "修复版本", "验证结果", "部署状态", "关联记录",
)


def text(value, fallback="未核实"):
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ValueError("文本字段必须是字符串")
    return value.strip() or fallback


def required(obj, key):
    value = text(obj.get(key), "")
    if not value:
        raise ValueError(f"缺少必填字段：{key}")
    return value


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("日期必须为 YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("日期必须为 YYYY-MM-DD")
    return value


def beijing_date(now=None):
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.tzinfo is None:
        raise ValueError("时间必须带时区")
    return now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()


def http_url(value):
    value = required({"url": value}, "url")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("链接必须是不含账号凭据的 HTTP(S) URL")
    return value


def paragraph(parent, value):
    p = ET.SubElement(parent, "p")
    lines = value.splitlines() or [""]
    p.text = lines[0]
    for line in lines[1:]:
        ET.SubElement(p, "br").tail = line
    return p


def table(parent, headers, rows):
    node = ET.SubElement(parent, "table")
    head = ET.SubElement(ET.SubElement(node, "thead"), "tr")
    for label in headers:
        paragraph(ET.SubElement(head, "th", {"background-color": "light-gray"}), label)
    body = ET.SubElement(node, "tbody")
    for row in rows:
        tr = ET.SubElement(body, "tr")
        for value in row:
            td = ET.SubElement(tr, "td", {"vertical-align": "top"})
            if isinstance(value, list):
                if not value:
                    paragraph(td, "未提供")
                for label, url in value:
                    p = ET.SubElement(td, "p")
                    ET.SubElement(p, "a", {"href": url}).text = label
            else:
                paragraph(td, value)
    return node


def render_record(spec):
    project = required(spec, "project_name")
    created = iso_date(spec["created_date"]) if "created_date" in spec else beijing_date()
    skills = spec.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("skills 必须是非空数组")
    root = ET.Element("record")
    ET.SubElement(root, "title").text = f"{project}技能维护记录_{created.replace('-', '')}"
    ET.SubElement(root, "h1", {"seq": "auto"}).text = "技能总览"
    overview, modules, seen_ids, seen_names = [], [], set(), set()
    for skill in skills:
        skill_id, name = required(skill, "id"), required(skill, "name")
        if skill_id in seen_ids or name in seen_names:
            raise ValueError("技能标识和名称必须唯一；请合并同一技能")
        seen_ids.add(skill_id)
        seen_names.add(name)
        repository = text(skill.get("repository"), "未提供")
        if repository.startswith(("http:", "https:")):
            repository = [(repository, http_url(repository))]
        overview.append((name, repository, required(skill, "current_version"), text(skill.get("branch"))))
        releases = skill.get("releases", [])
        if not isinstance(releases, list):
            raise ValueError("releases 必须是数组")
        rows, seen_versions = [], set()
        for release in releases:
            if release.get("status") != "released":
                raise ValueError("维护表仅接受 released 正式版本；请先剔除过程记录")
            version = required(release, "version")
            if version in seen_versions:
                raise ValueError(f"同一技能的同一正式版本只能一条：{skill_id} {version}")
            seen_versions.add(version)
            references = release.get("references", [])
            if not isinstance(references, list):
                raise ValueError("references 必须是数组")
            links = [(required(ref, "label"), http_url(ref.get("url"))) for ref in references]
            release_date = release.get("date")
            rows.append((
                name, iso_date(release_date) if release_date else "未核实",
                text(release.get("previous_version")), text(release.get("problem")),
                text(release.get("cause")), text(release.get("solution")), version,
                text(release.get("validation")), text(release.get("deployment")), links,
            ))
        if not rows:
            rows = [(name, "—", "—", "暂无已确认的正式版本记录", "—", "—", "—", "未核实", "未核实", [])]
        modules.append((name, rows))
    table(root, OVERVIEW_HEADERS, overview)
    ET.SubElement(root, "h1", {"seq": "auto"}).text = "技能维护记录"
    for name, rows in modules:
        ET.SubElement(root, "h2", {"seq": "auto"}).text = name
        table(root, RELEASE_HEADERS, rows)
    return "\n".join(ET.tostring(child, encoding="unicode") for child in root) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("输入与输出路径不能相同")
        spec = json.loads(args.input.read_text(encoding="utf-8"))
        xml = render_record(spec)
        args.output.write_text(xml, encoding="utf-8")
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        parser.exit(2, f"无法生成记录：{exc}\n")


if __name__ == "__main__":
    main()
