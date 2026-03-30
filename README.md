# jsm-compare

Jira Service Management (JSM) の自動化ルールをサンドボックスと本番環境で比較するCLIツール。

環境間のルール設定ドリフトを検出し、本番デプロイ前の差分チェックを自動化します。

## インストール

```bash
# インストール不要で即実行（uvx）
uvx jsm-compare rules --domain my-project --user me@example.com

# グローバルインストール
uv tool install jsm-compare

# pip
pip install jsm-compare
```

## 使い方

### 基本

```bash
# 環境変数で認証情報を設定
export JIRA_USER="me@example.com"
export JIRA_API_TOKEN="ATATT3x..."

# ドメイン指定（推奨）- sandbox/本番を自動展開
jsm-compare rules --domain my-project

# セクション指定
jsm-compare rules --domain my-project --section rules-overview
jsm-compare rules --domain my-project --section triggers
jsm-compare rules --domain my-project --section components

# フルホスト名指定（カスタムホスト名の場合）
jsm-compare rules --source my-project-sandbox.atlassian.net --target my-project.atlassian.net
```

`--domain my-project` は `--source my-project-sandbox.atlassian.net --target my-project.atlassian.net` に展開されます。

### オプション

| オプション | 環境変数 | デフォルト | 説明 |
|---|---|---|---|
| `--domain` | `JSM_DOMAIN` | - | ドメインプレフィックス。`{domain}-sandbox` と `{domain}` に展開 |
| `--source` | - | - | ソース環境のホスト名（`--domain`と排他） |
| `--target` | - | - | ターゲット環境のホスト名（`--domain`と排他） |
| `--user` | `JIRA_USER` | 必須 | Jira Cloud のメールアドレス |
| `--token` | `JIRA_API_TOKEN` | 必須 | Jira API トークン |
| `--section` | - | 全セクション | 比較セクション指定（`rules-overview` / `triggers` / `components`） |
| `--filter` | - | - | ルール名の前方一致フィルタ |
| `--mask` | - | OFF | Webhook URL等のセンシティブ値をマスク |
| `--raw` | - | OFF | 正規化後のJSON + unified diff表示（デバッグ用） |
| `--ignore-env` / `--no-ignore-env` | - | ON | 環境固有の差分を無視（customfield ID、ドメインURL、workspaceId、schemaId） |

### 認証

Jira Cloud APIトークンが必要です。
[Atlassian API トークンの管理](https://id.atlassian.com/manage-profile/security/api-tokens) から取得できます。

Automation REST APIにアクセスするには Jira管理者権限が必要です。

## 比較セクション

| セクション       | 比較内容                                         |
| ---------------- | ------------------------------------------------ |
| `rules-overview` | ルール名、state (ENABLED/DISABLED)、description  |
| `triggers`       | トリガーtype、スケジュール設定、JQL条件          |
| `components`     | 条件・アクション設定（環境固有のID/ARI自動除外） |

## 正規化

環境固有で比較不要なフィールドは自動的に除外されます。

### 除外フィールド

**ルールレベル**: id, clientKey, authorAccountId, actor, created, updated, ruleScope, labels, tags

**コンポーネントレベル**: id, parentId, conditionParentId, connectionId, checksum, schemaVersion

**トリガー**: eventFilters (ARI形式のプロジェクト参照)

## 出力例

```
JSM Automation Rules Comparison
  Source: my-project-sandbox.atlassian.net
  Target: my-project.atlassian.net
  Filter: [MyPrefix]
  Ignore env-specific: ON (customfield IDs, domain URLs, workspaceId, schemaId)

  [INFO]  Total rules: source=12, target=15
  [INFO]  Filtered: source=5, target=5

────────────────── Section 1: Rules Overview ──────────────────

  [INFO]  Only in source:
    [MyPrefix]Old Rule 20260101 [DISABLED]

  [MATCH] [MyPrefix]Recovery Notification 20260401
  [DIFF]  [MyPrefix]Customer Comment Notification 20260401
          description: "...managed by Admin User" -> "...Slack API : https://api.slack.com/..."

────────────────── Section 2: Triggers ─────────────────────

  All 4 triggers match.

────────────────── Section 3: Components ───────────────────

  [MATCH] [MyPrefix]Recovery Notification 20260401
  [DIFF]  [MyPrefix]Customer Comment Notification 20260401
          [1].value.channel: "#test-channel" -> "#production-channel"
          [1].value.webhookUrl: "https://hooks.slack.com/..." -> "https://hooks.slack.com/..."

Summary: 9 match, 2 diff, 1 source-only
Differences found.
```

## 終了コード

| コード | 意味                                  |
| ------ | ------------------------------------- |
| 0      | 全セクション一致                      |
| 1      | 差分あり                              |
| 2      | エラー（認証失敗、API接続エラーなど） |

## 動作要件

- Python 3.10+
- Jira Cloud 環境
- Jira管理者権限（Automation REST API アクセスに必要）

## ライセンス

MIT
