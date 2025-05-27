from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词自动应答系统",
    version="2.2",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """修复消息处理的核心版本"""
    
    def __init__(self, host: APIHost):
        self.host = host
        self.config = {'rules': []}
        self.pattern_cache = {}
        self.logger = host.ap.logger.getChild("WeChatReply")
        
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config", "wechat.yaml")
            if not os.path.exists(config_path):
                self.logger.error("配置文件未找到，使用空配置")
                return

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
                self.config = {'rules': config_data.get('rules', [])}
                
            # 预编译正则表达式
            for rule in self.config['rules']:
                try:
                    self.pattern_cache[rule['id']] = [
                        re.compile(pattern.strip(), re.IGNORECASE)
                        for pattern in rule.get('triggers', [])
                        if pattern.strip()
                    ]
                except re.error as e:
                    self.logger.error(f"规则 {rule.get('id', '未知')} 编译失败: {str(e)}")
                    
            self.logger.info(f"成功加载 {len(self.config['rules'])} 条应答规则")

        except Exception as e:
            self.logger.error(f"初始化异常: {str(e)}")

    def _get_message_text(self, ctx: EventContext):
        """通用消息提取方法"""
        try:
            # 兼容不同事件类型的消息获取
            if hasattr(ctx.event, 'query') and hasattr(ctx.event.query, 'message_chain'):
                return ''.join(
                    str(p) for p in ctx.event.query.message_chain
                    if isinstance(p, Plain)
                ).strip()
            elif hasattr(ctx.event, 'text_message'):
                return ctx.event.text_message.strip()
            return ""
        except Exception as e:
            self.logger.error(f"消息提取失败: {str(e)}")
            return ""

    def _build_response(self, rule):
        """安全构建响应消息"""
        try:
            chain = []
            for item in rule.get('response', []):
                if item['type'] == 'text':
                    content = '\n'.join(line.strip() for line in str(item.get('content', '')).split('\n') if line.strip())
                    if content: chain.append(Plain(content))
                elif item['type'] == 'image' and item.get('url'):
                    chain.append(Image(url=item['url']))
            return MessageChain(chain) if chain else None
        except Exception as e:
            self.logger.error(f"构建响应失败: {str(e)}")
            return None

    def _match_message(self, text):
        """执行消息匹配"""
        try:
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', text).strip()
            for rule in self.config['rules']:
                for pattern in self.pattern_cache.get(rule['id'], []):
                    if pattern.search(clean_text):
                        return rule
            return None
        except Exception as e:
            self.logger.error(f"匹配异常: {str(e)}")
            return None

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """统一消息处理入口"""
        try:
            # 提取消息文本
            message = self._get_message_text(ctx)
            if not message:
                return

            # 执行匹配
            matched_rule = self._match_message(message)
            if not matched_rule:
                return

            # 构建并发送响应
            if response := self._build_response(matched_rule):
                ctx.add_return("reply", response)
                ctx.prevent_default()  # 关键阻断调用
                self.logger.info(f"已阻断并响应: {message[:15]}...")

        except Exception as e:
            self.logger.error(f"处理异常: {str(e)}")
            ctx.prevent_default()  # 异常时也阻断

    def __del__(self):
        self.logger.info("插件安全卸载")
