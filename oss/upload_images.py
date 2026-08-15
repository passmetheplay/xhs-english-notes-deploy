#!/usr/bin/env python3
"""Sync the English note images to Alibaba Cloud OSS."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("XHS_OSS_CONFIG", "/Users/le/code/english_study_utils/infra/oss/oss_config.json"))
SOURCE = Path(os.environ.get("XHS_SOURCE_ROOT", "/Users/le/code/obsidian-notes/社媒/小红书轮播图"))
DEFAULT_BUCKET = "listeneveryday"
DEFAULT_ENDPOINT = "oss-cn-shenzhen.aliyuncs.com"
DEFAULT_PREFIX = "xhs-english-notes"
IMAGE_REF = re.compile(r'(?P<q>["\'])(?P<path>notes/[^"\']+\.(?:png|webp))(?P=q)')


class UploadError(RuntimeError):
    pass


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["oss_access_key_id"] = data.get("oss_access_key_id") or os.environ.get("OSS_ACCESS_KEY_ID")
    data["oss_access_key_secret"] = data.get("oss_access_key_secret") or os.environ.get("OSS_ACCESS_KEY_SECRET")
    if not data["oss_access_key_id"] or not data["oss_access_key_secret"]:
        raise UploadError("缺少 OSS 凭证")
    return data


def sign(*, method: str, bucket: str, endpoint: str, key: str, content_type: str, config: dict, public_read: bool) -> tuple[str, dict[str, str]]:
    expires = str(int(time.time()) + 3600)
    canonical = f"/{bucket}/{key}"
    headers: dict[str, str] = {}
    canonical_headers = ""
    if public_read:
        headers["x-oss-object-acl"] = "public-read"
        canonical_headers = "x-oss-object-acl:public-read\n"
    text = "\n".join([method, "", content_type, expires, canonical_headers + canonical])
    digest = hmac.new(config["oss_access_key_secret"].encode(), text.encode(), hashlib.sha1).digest()
    signature = quote(base64.b64encode(digest).decode(), safe="")
    url = f"https://{bucket}.{endpoint}/{quote(key, safe='/-_.~')}?OSSAccessKeyId={config['oss_access_key_id']}&Expires={expires}&Signature={signature}"
    return url, headers


def upload(payload: bytes, *, key: str, content_type: str, bucket: str, endpoint: str, config: dict, public_read: bool) -> None:
    url, headers = sign(method="PUT", bucket=bucket, endpoint=endpoint, key=key, content_type=content_type, config=config, public_read=public_read)
    headers.update({"Content-Type": content_type, "Content-Length": str(len(payload))})
    response = requests.put(url, data=payload, headers=headers, timeout=(30, 300))
    if response.status_code >= 300:
        raise UploadError(f"上传失败 {key}: HTTP {response.status_code}")


def oss_url(bucket: str, endpoint: str, prefix: str, path: str) -> str:
    relative = path.removeprefix("notes/")
    return f"https://{bucket}.{endpoint}/{quote(prefix + '/' + relative, safe='/-_.~')}"


def rewrite_index(output: Path, bucket: str, endpoint: str, prefix: str) -> int:
    html = (ROOT / "index.html").read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        return f'{match.group("q")}{oss_url(bucket, endpoint, prefix, match.group("path"))}{match.group("q")}'

    rewritten, count = IMAGE_REF.subn(replace, html)
    output.write_text(rewritten, encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--source-root", type=Path, default=SOURCE)
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--public-read", action="store_true")
    parser.add_argument("--write-index", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    manifest = json.loads((ROOT / "publish-manifest.json").read_text(encoding="utf-8"))
    bucket = args.bucket or config.get("oss_bucket") or DEFAULT_BUCKET
    endpoint = (config.get("bucket_endpoints") or {}).get(bucket) or config.get("oss_endpoint") or DEFAULT_ENDPOINT
    endpoint = endpoint.removeprefix("https://").rstrip("/")
    jobs = []
    for note in manifest["notes"]:
        for image in note["images"]:
            source = args.source_root / image["source"]
            if not source.is_file():
                raise UploadError(f"找不到源图: {source}")
            jobs.append((source, image["original"]["path"], image["web"]["path"]))
    print(f"源目录: {args.source_root}")
    print(f"待处理图片: {len(jobs) * 2} 张（{len(jobs)} PNG + {len(jobs)} WebP）")
    print(f"OSS 目标: oss://{bucket}/{args.prefix.strip('/')}/")
    if args.upload and not args.dry_run:
        with tempfile.TemporaryDirectory(prefix="xhs-oss-webp-") as temp:
            for index, (source, original, web) in enumerate(jobs, 1):
                original_key = f"{args.prefix.strip('/')}/{original.removeprefix('notes/')}"
                web_key = f"{args.prefix.strip('/')}/{web.removeprefix('notes/')}"
                upload(source.read_bytes(), key=original_key, content_type="image/png", bucket=bucket, endpoint=endpoint, config=config, public_read=args.public_read)
                webp = Path(temp) / f"{index}.webp"
                with Image.open(source) as image:
                    image.save(webp, "WEBP", quality=82, method=6)
                upload(webp.read_bytes(), key=web_key, content_type="image/webp", bucket=bucket, endpoint=endpoint, config=config, public_read=args.public_read)
                print(f"[{index}/{len(jobs)}] 已上传 {original_key} + {web_key}")
        print("上传完成。")
    else:
        print("检查模式：不会写入 OSS。")
    if args.write_index:
        count = rewrite_index(args.write_index, bucket, endpoint, args.prefix.strip("/"))
        print(f"已生成 OSS 页面: {args.write_index}（替换 {count} 个图片地址）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UploadError as error:
        raise SystemExit(f"错误: {error}")
