# 肾病经典及前沿治疗

这是治疗方案查询工具的可发布版本。GitHub 只上传 Web/API 运行代码；查询数据由 OSS 提供。

不包含：完整知识库、原文 PDF、书籍、抽取侧车、源文件缓存、QA 审核表、本地绝对路径或内部 SQLite。

`compiled_public/*.json` 是脱敏后的公开查询数据，发布时应上传到 OSS；这些 JSON 已被 `.gitignore` 排除，不进入 GitHub。

## 本地运行

```bash
python server.py --host 127.0.0.1 --port 8785 --compiled-dir compiled_public --public-mode
```

## Render + OSS

Render 运行代码，启动时从 OSS 拉取公开 JSON：

```bash
COMPILED_DATA_URL_BASE=https://<bucket>.<endpoint>/<prefix> \
python server.py --host 0.0.0.0 --port $PORT --compiled-dir /tmp/renal-treatment-compiled --public-mode
```

## Render

`render.yaml` 已配置为使用 `/tmp/renal-treatment-compiled` 和 `--public-mode` 启动；需要在 Render 环境变量里设置 `COMPILED_DATA_URL_BASE`。

## API

- `GET /api/health`
- `GET /api/diseases?q=<疾病名>`
- `GET /api/query?q=<自然语言问题>`
- `GET /api/evidence?disease=<disease_key>`
- `GET /api/payer?disease=<disease_key>`
