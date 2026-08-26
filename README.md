# MCP-сервер: Order

**Стек:** 
- Python 3.10+
- MCP SDK: `mcp>=1.27,<2`
- Менеджер окружения: venv + pip

**Запуск:** 
```
    python -m venv .venv
    source .venv/bin/activate
    pip install -e .
    python mcp/order_server.py
```
**Инструменты:**
`get_order_state`, `change_order_status`, `set_payment_method`


**Источник данных:** `mcp/orders.json`