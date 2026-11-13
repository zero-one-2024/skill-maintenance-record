"""Observable output checks for the project record renderer."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "render_record.py"
spec = importlib.util.spec_from_file_location("maintenance_renderer", SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def words(node):
    return "".join(node.itertext())


def cells(table):
    return [[words(c) for c in row] for row in table.findall("tbody/tr")]


def snapshot():
    return {
        "project_name": "立中项目", "created_date": "2026-11-12",
        "skills": [{
            "id": "process", "name": "工序监测（扒渣链）",
            "repository": "https://example.com/process", "current_version": "1.0.8；已部署",
            "branch": "main", "releases": [{
                "status": "released", "date": "2026-11-12", "previous_version": "1.0.7",
                "version": "1.0.8", "problem": "有效作业漏记。", "cause": "结算耦合。",
                "solution": "分离作业记录与结算。", "validation": "报告称回归通过；长期效果待观察。",
                "deployment": "已部署；业务验收未完成。",
                "references": [{"label": "发布与验证", "url": "https://example.com/releases/1.0.8"}],
            }],
        }, {
            "id": "ppe", "name": "吹堵塞棒监测", "current_version": "1.2.10；生产1.2.9",
            "releases": [
                {"status": "released", "version": "1.2.10", "validation": "4张仍未知；完整时段未验证。"},
                {"status": "released", "version": "1.2.9", "date": "2026-11-10"},
            ],
        }],
    }


class RenderRecordTests(unittest.TestCase):
    def tree(self, data=None):
        return ET.fromstring("<root>" + renderer.render_record(data or snapshot()) + "</root>")

    def test_name_two_modules_and_separate_skill_tables(self):
        root = self.tree()
        self.assertEqual(words(root[0]), "立中项目技能维护记录_20261112")
        self.assertEqual([words(h) for h in root.findall("h1")], ["技能总览", "技能维护记录"])
        self.assertEqual([words(h) for h in root.findall("h2")], ["工序监测（扒渣链）", "吹堵塞棒监测"])
        self.assertTrue(all(e.tag in ("title", "h1", "h2", "table") for e in root))
        tables = root.findall("table")
        self.assertEqual([len(t.findall("thead/tr/th")) for t in tables], [4, 10, 10])
        self.assertEqual([len(cells(t)) for t in tables], [2, 1, 2])

    def test_patch_releases_retained_once_with_limits_and_current_state(self):
        tables = self.tree().findall("table")
        self.assertEqual(cells(tables[2])[0][6], "1.2.10")
        self.assertEqual(cells(tables[2])[1][6], "1.2.9")
        self.assertEqual(cells(tables[0])[1][2], "1.2.10；生产1.2.9")
        self.assertEqual(cells(tables[2])[0][7], "4张仍未知；完整时段未验证。")
        self.assertEqual(cells(tables[1])[0][8], "已部署；业务验收未完成。")

    def test_same_version_across_skills_allowed_but_duplicate_within_skill_rejected(self):
        data = snapshot()
        data["skills"][1]["releases"][0]["version"] = "1.0.8"
        self.tree(data)
        data["skills"][0]["releases"].append(deepcopy(data["skills"][0]["releases"][0]))
        with self.assertRaisesRegex(ValueError, "同一正式版本"):
            renderer.render_record(data)

    def test_process_and_candidate_rows_rejected(self):
        for status in ("candidate", "debug", "testing", "", None):
            with self.subTest(status=status):
                data = snapshot()
                data["skills"][0]["releases"][0]["status"] = status
                with self.assertRaisesRegex(ValueError, "过程记录"):
                    renderer.render_record(data)

    def test_missing_facts_not_invented(self):
        row = cells(self.tree().findall("table")[2])[0]
        self.assertEqual(row[1:6], ["未核实"] * 5)
        self.assertEqual(row[8:], ["未核实", "未提供"])

    def test_empty_release_history_does_not_create_fake_version(self):
        data = snapshot()
        data["skills"][0]["releases"] = []
        row = cells(self.tree(data).findall("table")[1])[0]
        self.assertEqual(row[3], "暂无已确认的正式版本记录")
        self.assertEqual(row[6], "—")

    def test_text_and_links_roundtrip_without_xml_injection(self):
        data = snapshot()
        value = 'A < B & C "quoted"\n<p>不能插入正文</p>'
        data["skills"][0]["releases"][0]["solution"] = value
        url = 'https://example.com/report?a=1&b="2"'
        data["skills"][0]["releases"][0]["references"][0]["url"] = url
        root = self.tree(data)
        cell = root.findall("table")[1].findall("tbody/tr/td")[5]
        self.assertEqual(words(cell), value.replace("\n", ""))
        self.assertEqual(len(cell.findall("p")), 1)
        self.assertEqual(len(cell.findall("p/br")), 1)
        self.assertEqual(root.findall("table")[1].find(".//a").get("href"), url)

    def test_bad_reference_links_rejected(self):
        for url in ("javascript:alert(1)", "file:///tmp/report", "https://user:secret@example.com/x"):
            with self.subTest(url=url):
                data = snapshot()
                data["skills"][0]["releases"][0]["references"][0]["url"] = url
                with self.assertRaises(ValueError):
                    renderer.render_record(data)

    def test_creation_date_uses_beijing_and_is_stable_when_explicit(self):
        instant = datetime(2026, 11, 12, 16, 30, tzinfo=timezone.utc)
        self.assertEqual(renderer.beijing_date(instant), "2026-11-13")
        self.assertTrue(words(self.tree().find("title")).endswith("_20261112"))
        for value in ("2026-02-30", "20261112", "2026-1-2", ""):
            with self.subTest(value=value):
                data = snapshot()
                data["created_date"] = value
                with self.assertRaises(ValueError):
                    renderer.render_record(data)

    def test_invalid_identity_or_missing_version_rejected(self):
        for change in ("duplicate_id", "duplicate_name", "blank_version", "empty_project"):
            with self.subTest(change=change):
                data = snapshot()
                if change == "duplicate_id":
                    data["skills"][1]["id"] = "process"
                elif change == "duplicate_name":
                    data["skills"][1]["name"] = data["skills"][0]["name"]
                elif change == "blank_version":
                    data["skills"][0]["releases"][0]["version"] = " "
                else:
                    data["project_name"] = " "
                with self.assertRaises(ValueError):
                    renderer.render_record(data)

    def test_render_does_not_change_input(self):
        data = snapshot()
        original = deepcopy(data)
        first = renderer.render_record(data)
        self.assertEqual(data, original)
        self.assertEqual(renderer.render_record(data), first)

    def test_documented_example_renders_and_does_not_add_project_suffix(self):
        reference = (SKILL / "references" / "record-format.md").read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.*?)\n```", reference, re.S).group(1))
        title = words(self.tree(example).find("title"))
        self.assertEqual(title, "示例项目技能维护记录_20261112")
        example["project_name"] = "一个名称超过十五个字符的项目完整名称"
        self.assertTrue(words(self.tree(example).find("title")).startswith(example["project_name"]))

    def test_cli_rejects_input_output_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "record.json"
            original = json.dumps(snapshot(), ensure_ascii=False)
            source.write_text(original, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(source)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_cli_output_and_invalid_input_keeps_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "input.json", Path(temp) / "draft.xml"
            data = snapshot()
            source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "--input", str(source), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = output.read_text(encoding="utf-8")
            self.assertEqual(expected, renderer.render_record(data))
            data["skills"][0]["releases"].append(deepcopy(data["skills"][0]["releases"][0]))
            source.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), expected)

    def test_readme_links_resolve_inside_standalone_skill(self):
        for filename in ("README.md", "README.zh-CN.md"):
            content = (SKILL / filename).read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(readme=filename, target=target):
                    destination = (SKILL / target.split("#", 1)[0]).resolve()
                    self.assertTrue(destination.is_relative_to(SKILL.resolve()))
                    self.assertTrue(destination.is_file())

    def test_readme_renderer_commands_and_table_headers_match_actual_output(self):
        reference = (SKILL / "references" / "record-format.md").read_text(encoding="utf-8")
        example = json.loads(re.search(r"```json\n(.*?)\n```", reference, re.S).group(1))
        for filename in ("README.md", "README.zh-CN.md"):
            with self.subTest(readme=filename), tempfile.TemporaryDirectory() as temp:
                content = (SKILL / filename).read_text(encoding="utf-8")
                source, output = Path(temp) / "record.json", Path(temp) / "draft.xml"
                source.write_text(json.dumps(example, ensure_ascii=False), encoding="utf-8")
                line = next(line for line in content.splitlines()
                            if line.startswith("python3 scripts/render_record.py "))
                command = shlex.split(line)
                command[0] = sys.executable
                command[command.index("--input") + 1] = str(source)
                command[command.index("--output") + 1] = str(output)
                result = subprocess.run(command, cwd=SKILL, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                root = ET.fromstring("<root>" + output.read_text(encoding="utf-8") + "</root>")
                documented_headers = [
                    [cell.strip() for cell in line.strip().strip("|").split("|")]
                    for line in content.splitlines() if line.startswith("| 技能名称 |")
                ]
                actual_headers = [[words(cell) for cell in table.findall("thead/tr/th")]
                                  for table in root.findall("table")]
                self.assertEqual(documented_headers, actual_headers)


if __name__ == "__main__":
    unittest.main()
