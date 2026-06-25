# 肾病经典及前沿治疗

这是治疗方案查询工具的可发布版本。GitHub 只上传 Web/API 运行代码；查询数据由 OSS 提供，推荐保持 OSS 对象私有，由 Render 使用只读 RAM Key 拉取。

不包含：完整知识库、原文 PDF、书籍、抽取侧车、源文件缓存、QA 审核表、本地绝对路径或内部 SQLite。

`compiled_public/*.json` 是脱敏后的可发布查询数据，发布时上传到 OSS；这些 JSON 已被 `.gitignore` 排除，不进入 GitHub。

## 本地运行

```bash
python server.py --host 127.0.0.1 --port 8785 --compiled-dir compiled_public --public-mode
```

## Render + OSS

Render 运行代码，启动时从 OSS 拉取查询 JSON。推荐方式是 OSS 私有对象 + RAM 只读 Key：

```bash
ALIYUN_OSS_BUCKET=renal \
ALIYUN_OSS_ENDPOINT=https://oss-cn-hongkong.aliyuncs.com \
COMPILED_DATA_OSS_PREFIX=public/renal-treatment-query/compiled_public \
python server.py --host 0.0.0.0 --port $PORT --compiled-dir /tmp/renal-treatment-compiled --public-mode
```

## Render

`render.yaml` 已配置为使用 `/tmp/renal-treatment-compiled` 和 `--public-mode` 启动。

如果 OSS 对象保持私有，不填 `COMPILED_DATA_URL_BASE`，改填 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`，并保留 `COMPILED_DATA_OSS_PREFIX=public/renal-treatment-query/compiled_public`。

Render 运行只需要 `docs/oss_ram_policy_render_readonly.json` 中的只读权限。上传数据的本地发布账号才需要 `docs/oss_ram_policy_minimal.json` 中的写入权限。

## 后续更新流程

### 更新查询数据

```bash
cd /Users/liwei/Desktop/renal-treatment-query-product
./scripts/update_public_data_from_kb.sh
./scripts/upload_public_json_to_oss.py --dry-run
./scripts/upload_public_json_to_oss.py
./scripts/trigger_render_deploy.py
```

`compiled_public/` 只作为本地待上传数据目录，已被 `.gitignore` 排除，不提交到 GitHub。

如果旧项目的 OSS key 上传失败，请给 RAM 用户增加 `docs/oss_ram_policy_minimal.json` 中的新前缀权限，然后把 key 写入 `.env.upload`。

### 更新代码

```bash
cd /Users/liwei/Desktop/renal-treatment-query-product
git status
git add server.py query_treatment_index.py static render.yaml README.md scripts
git commit -m "Update renal treatment query app"
git push origin main
```

## API

- `GET /api/health`
- `GET /api/diseases?q=<疾病名>`
- `GET /api/query?q=<自然语言问题>`
- `GET /api/evidence?disease=<disease_key>`
- `GET /api/payer?disease=<disease_key>`
