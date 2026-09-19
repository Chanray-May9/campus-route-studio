# 轨迹后端：Cloudflare Workers + D1

接口：`GET /api/routes` 用于读取公开轨迹，`GET/POST/DELETE /api/admin/routes` 需要 `CR_ADMIN_TOKEN`；`/admin` 是管理页面。定位回放不会向服务器持续上报。

安装 Node.js 24，进入本目录执行 npm ci 与 npm test。管理员密钥放在本地 .dev.vars（随机至少 32 字符，不能提交源码）。

1. npx wrangler login，浏览器完成官方授权。
2. npx wrangler d1 create campus-route-db，把返回的数据库 ID 填入 wrangler.jsonc，并填写自己的 account_id。
3. npx wrangler d1 migrations apply campus-route-db --remote。
4. 在源码目录外创建 secrets.json，仅包含 CR_ADMIN_TOKEN。
5. npx wrangler deploy --secrets-file 私有secrets.json。
6. 将返回的 HTTPS 地址写到 mobile/assets/config.json 的 backend 字段，重新构建 APK。

本地验证：npx wrangler d1 migrations apply campus-route-db --local，npx wrangler dev。最多发布 50 条结构化路线，每条 2–10000 点。不能下发脚本或 APK。

Workers 与 D1 的资源额度及计费规则以 Cloudflare 当前文档为准：[Workers 限制](https://developers.cloudflare.com/workers/platform/limits/)、[D1 额度](https://developers.cloudflare.com/d1/platform/pricing/)。
