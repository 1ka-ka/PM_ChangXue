"""短信发送适配层（V1.4）：dev / aliyun 双实现，调用方无感切换。

- dev：验证码写日志（零依赖，本地联调用；接口响应同时带 debug_code）
- aliyun：阿里云短信 SDK（pip install ".[sms]"），懒加载——dev 环境无需安装
- 配置见 Settings.SMS_*；发送失败抛 BizError，由调用方决定是否落库
"""

import logging

from app.core.config import settings
from app.core.exceptions import BizError, ErrCode

logger = logging.getLogger("changxue.sms")


def send(phone: str, code: str) -> None:
    """发送验证码：失败抛 50001（调用方不落库，用户可立即重试）。"""
    if settings.SMS_PROVIDER == "aliyun":
        _send_aliyun(phone, code)
    else:
        logger.info(
            "[SMS][dev] 手机号 %s 验证码 %s（%s 分钟内有效）",
            phone,
            code,
            settings.SMS_CODE_TTL_MINUTES,
        )


def _send_aliyun(phone: str, code: str) -> None:
    try:
        import json

        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_dysmsapi20170525.models import SendSmsRequest
        from alibabacloud_tea_openapi.models import Config
    except ImportError:
        logger.exception("阿里云短信 SDK 未安装（pip install .[sms]）")
        raise BizError(ErrCode.INTERNAL, "短信服务未正确配置，请联系管理员")

    if not all(
        (
            settings.SMS_ALIYUN_ACCESS_KEY_ID,
            settings.SMS_ALIYUN_ACCESS_KEY_SECRET,
            settings.SMS_ALIYUN_SIGN_NAME,
            settings.SMS_ALIYUN_TEMPLATE_CODE,
        )
    ):
        raise BizError(ErrCode.INTERNAL, "短信服务未正确配置，请联系管理员")

    client = Client(
        Config(
            access_key_id=settings.SMS_ALIYUN_ACCESS_KEY_ID,
            access_key_secret=settings.SMS_ALIYUN_ACCESS_KEY_SECRET,
            endpoint="dysmsapi.aliyuncs.com",
        )
    )
    resp = client.send_sms(
        SendSmsRequest(
            phone_numbers=phone,
            sign_name=settings.SMS_ALIYUN_SIGN_NAME,
            template_code=settings.SMS_ALIYUN_TEMPLATE_CODE,
            template_param=json.dumps({"code": code}),
        )
    )
    if resp.body.code != "OK":
        logger.warning("阿里云短信发送失败 phone=%s code=%s msg=%s", phone, resp.body.code, resp.body.message)
        raise BizError(ErrCode.INTERNAL, "短信发送失败，请稍后再试")
    logger.info("[SMS][aliyun] 发送成功 phone=%s", phone)
