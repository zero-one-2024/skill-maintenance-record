# Skill Maintenance Records

[English](README.md) | [简体中文](README.zh-CN.md)

A Codex skill for creating and updating a project's skill maintenance record in Feishu. It supports both business monitoring skills and Codex Skills. Records contain a current skill overview and concise release history, with one row per confirmed official version rather than a log of debugging steps.

## Requirements and installation

- Codex with access to the relevant project materials and referenced chats.
- For Feishu: the `lark-doc` skill, `lark-cli`, and an authenticated user with permission to create or edit the target document. These dependencies are not bundled here.
- For the optional local renderer and tests: Python 3.9 or later with `Asia/Shanghai` timezone data. No third-party Python packages are required.

Install into the default local skills directory:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/zero-one-2024/skill-maintenance-record.git ~/.codex/skills/skill-maintenance-record
```

If `CODEX_HOME` is customized, use its `skills` directory. If this skill is already installed, update that installation; preserve a symbolic link to a development workspace instead of creating a second copy.

## Invoke the skill

Supply the project name and relevant chats, release reports, or files. You do not need to prepare JSON manually.

Create the project's first record:

```text
Use $skill-maintenance-record to prepare the skill maintenance record for
示例项目 from this chat and the attached release reports. Save it in Feishu
My Library. Include only key official releases.
```

Update an existing record:

```text
Use $skill-maintenance-record to add the inspection skill's 1.2.10 release
to <maintenance document URL>, using <release report>. Update the overview,
keep the other skills and previous releases, and retain one row for 1.2.10.
```

Prepare a local draft:

```text
Use $skill-maintenance-record to draft the maintenance record for 示例项目
from the supplied files. Local draft only; do not write to Feishu.
```

Invoking the skill to compile a record authorizes creating it or updating the specified record. An existing destination in the project rules is reused. Without an established destination, the skill creates the project's first record in **Feishu My Library** by default. A later invocation or a new calendar day does not by itself call for a new document. An explicit request for a separate snapshot takes precedence.

## Record name and format

New document names follow this literal pattern:

```text
{project_name}技能维护记录_{YYYYMMDD}
立中项目技能维护记录_20261112
```

The suffix is the document creation date in `Asia/Shanghai`, not the release date. The project name is used as supplied, without adding another “项目” or imposing a 15-character limit. Updating an existing record preserves its creation date and title unless a rename is requested.

The default document uses the Chinese headings and column names below. There are exactly two top-level sections; all content other than headings belongs in tables. These Markdown tables illustrate the format; Feishu output uses native tables and automatically numbered headings. The sample data is fictional.

### 1. 技能总览 — Skill overview

One row per skill, reflecting its latest confirmed version and state:

| 技能名称 | 仓库地址 | 当前版本 | 分支说明 |
| --- | --- | --- | --- |
| 巡检监测 | https://example.com/team/inspection | 1.2.10；测试环境已部署 | main |

The columns are skill name, repository, current version, and branch notes. If code and deployed versions differ, state both briefly; a code version does not prove deployment.

### 2. 技能维护记录 — Skill maintenance history

Each skill has its own subsection and ten-column table, with one concise row per official version:

| 技能名称 | 修复日期 | 问题版本 | 问题描述 | 原因分析 | 解决方案 | 修复版本 | 验证结果 | 部署状态 | 关联记录 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 巡检监测 | 2026-11-12 | 1.2.9 | 部分作业漏记。 | 完成判断耦合。 | 独立判断作业完成并优化调度。 | 1.2.10 | 报告称回归通过；完整时段未验证。 | 测试环境已部署；生产未部署，业务验收未完成。 | [发布报告](https://example.com/releases/1.2.10) |

The ten columns cover skill name, release date, previous version, issue or requirement, confirmed cause, solution, released version, validation, deployment, and supporting records. For a new capability, describe the requirement and use “新增能力” as the cause; the first release uses “初始版本” as its previous version. Unknown facts remain “未核实” (unverified) or “未提供” (not provided).

“Key release” does not mean only a semantic major version: `1.2.9 → 1.2.10` can be a key official release. Consolidate work on the same skill and version into one row, updating that row when validation is supplemented. Preserve distinct historical releases. Omit candidates, debugging rounds, intermediate tests, full source code, and process narratives. Keep important gaps such as incomplete validation or failed business acceptance.

See [Record format and input schema](references/record-format.md) for field definitions and a fictional JSON example. The skill instructions and that reference are in Chinese.

## Optional local renderer

The assistant can turn verified, consolidated JSON into native-table XML. From the repository root, replace these paths with actual input and output paths:

```bash
python3 scripts/render_record.py --input /absolute/path/record.json --output /absolute/path/draft.xml
```

For Feishu creation, use the dedicated draft workspace allocated by the `lark-doc` workflow. The renderer preserves input order, rejects duplicate versions within a skill and entries whose status is not `released`, and marks missing facts without inventing results. It does not infer the latest version or verify whether a release claim is true. Input and output paths must differ; a valid render writes to the specified output path and may replace an existing local file.

The renderer performs no Feishu operations. Use the editing workflow for existing documents, preserving other skills, historical versions, links, and resources with targeted changes. Do not overwrite a whole online document with renderer output. Cloud completion requires writing and reading back the affected tables; successful local parsing alone is insufficient. If dependencies, authentication, or permissions are unavailable, the skill retains a local draft and reports the remaining work.

## Tests

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover naming, Beijing time, table structure, version uniqueness, candidate rejection, missing facts, validation limits, XML escaping, CLI behavior, README links, and documented renderer commands. They run locally and do not create or modify Feishu documents.
