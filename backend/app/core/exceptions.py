"""统一业务异常与错误码注册表（技术细节文档 §2.2）。

错误码分段：
  0      成功
  400xx  通用参数/校验错误
  401xx  认证
  403xx  权限
  409xx  业务规则冲突
  500xx  服务器错误

HTTP 状态码约定（技术细节文档 §2.1）：业务错误统一 200 用 code 区分；
仅 401xx→401、500xx→500 使用真实 HTTP 状态码。
"""


class ErrCode:
    OK = 0

    # ---- 400xx 通用 ----
    BAD_REQUEST = 40001  # 参数错误
    NOT_FOUND = 40002  # 资源不存在或已删除
    SENSITIVE_WORD = 40003  # 内容含违禁词
    PHONE_EXISTS = 40004  # 手机号已注册
    FILE_INVALID = 40005  # 文件类型/大小超限
    RATE_LIMITED = 40006  # 请求过于频繁（埋点限流，HTTP 429）

    # ---- 401xx 认证 ----
    BAD_CREDENTIALS = 40101  # 账号或密码错误
    TOKEN_INVALID = 40102  # 未登录或 token 失效
    ACCOUNT_BANNED = 40103  # 账号已被封禁

    # ---- 403xx 权限 ----
    FORBIDDEN = 40301  # 无权操作（非资源所有者）
    NOT_ADMIN = 40302  # 非管理员

    # ---- 409xx 业务冲突 ----
    ACCEPT_LIMIT = 40901  # 采纳数已达上限（3 个）
    CREDIT_INSUFFICIENT = 40902  # 积分不足
    DUPLICATE_ACTION = 40903  # 重复操作（重复举报等）
    DUPLICATE_ANSWER = 40904  # 重复回答 / 自问自答
    ANSWER_EDIT_LOCKED = 40905  # 已被采纳的回答不可编辑
    ANSWER_DELETE_LOCKED = 40906  # 已被采纳的回答不可删除
    ALREADY_ACCEPTED = 40907  # 该回答已被采纳
    TARGET_NOT_ACCEPTED = 40908  # 目标回答未被采纳（设最佳前置条件）
    COMMENT_NESTING = 40909  # 评论层级超限（二层封顶）
    FAVORITE_NOT_ALLOWED = 40910  # 评论不可收藏
    REPORT_HANDLED = 40911  # 举报已被处理
    RECALL_EXCEED_BALANCE = 40912  # 追回积分超余额（追回至 0，流水记实际值）
    LOW_QUALITY_ANSWER = 40913  # AI 判定回答质量过低（V1.3）

    # ---- 500xx 服务器 ----
    INTERNAL = 50001


class BizError(Exception):
    """业务异常：由全局异常处理器统一转为响应信封。"""

    def __init__(self, code: int, msg: str, *, http_status: int | None = None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        if http_status is None:
            if code >= 50000:
                http_status = 500
            elif 40100 <= code < 40200:
                http_status = 401
            else:
                http_status = 200
        self.http_status = http_status
