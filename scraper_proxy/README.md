# Amazon Scraper Proxy

部署在 Windows 虚拟机上的抓取代理服务，作为主服务的「虚拟 IP」使用。

## 快速启动

1. 将整个 `scraper_proxy` 文件夹复制到 Windows 虚拟机
2. 双击 `start.bat` 即可（自动创建虚拟环境、安装依赖、启动服务）

或手动：
```bash
pip install -r requirements.txt
python scraper_server.py --port 9100
```

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/scrape` | 抓取产品数据 |

### POST /scrape

请求：
```json
{"asin": "B0XXXXXXXX", "marketplace": "US"}
```

响应：
```json
{
  "success": true,
  "data": {
    "asin": "B0XXXXXXXX",
    "title": "Product Title...",
    "brand": "Brand",
    "price": "$29.99",
    "bullet_points": ["..."],
    "description": "...",
    ...
  }
}
```

## 配置

主服务端在 `.env` 中配置虚拟机地址：
```
LAI_SCRAPER_PROXY_URL=http://虚拟机IP:9100
```

## 防火墙

确保虚拟机的 9100 端口对主服务器开放：
- Windows 防火墙 → 入站规则 → 新建规则 → 端口 → TCP 9100 → 允许连接
