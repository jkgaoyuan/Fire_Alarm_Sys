"""
Pydantic 可变默认值必须是「实例」，不能是「类型」

`Field(default=list)` 在 Pydantic v2 里**不会**被当作工厂调用 —— 缺省时字段值就是
`list` 这个类型对象本身（Pydantic v2 默认不校验 default，所以也不会报错），
于是 `attachments or []` 的 `or []` 永远不生效（类型对象是 truthy），
最终在写库/序列化时炸成 `TypeError: Object of type type is not JSON serializable`。

正确写法是 `Field(default_factory=list)`。

注意区分：**SQLAlchemy 列**上的 `default=list` 是正确的 —— SQLAlchemy 确实会把
可调用对象当工厂调用（见 models/emergency.py 的 attachments 列）。本文件只钉 Pydantic。
"""

from app.schemas.emergency import EmergencyTimelineCreate
from app.schemas.linkage import LinkagePlanCreate


def test_emergency_timeline_attachments_default_is_instance():
    payload = EmergencyTimelineCreate(node_type="check_in")

    assert payload.attachments == []
    assert isinstance(payload.attachments, list)


def test_linkage_plan_actions_default_is_instance():
    payload = LinkagePlanCreate(plan_name="测试预案", org_id=1)

    assert payload.actions == []
    assert isinstance(payload.actions, list)
