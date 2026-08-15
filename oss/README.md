# 小红书英语口语图片 OSS

这个目录负责把网页图片同步到阿里云 OSS。GitHub 仓库继续保留 PNG 原图和 WebP 备份，线上页面引用 OSS 地址。

预检：

```bash
python3 oss/upload_images.py \
  --source-root "/Users/le/code/obsidian-notes/社媒/小红书轮播图" \
  --dry-run
```

上传并生成 OSS 图片版页面：

```bash
python3 oss/upload_images.py \
  --source-root "/Users/le/code/obsidian-notes/社媒/小红书轮播图" \
  --upload --public-read --write-index index.html
```

默认目标是 `oss://listeneveryday/xhs-english-notes/`。脚本根据 `publish-manifest.json` 映射 22 篇笔记，并为 PNG 生成 quality 82 的 WebP 预览。
