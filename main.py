from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词回复插件",
    version="3.1",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """修复默认回复问题的最终版本"""
    
    def __init__(self, host: APIHost):
        self.host = host
        self.config = {'rules': []}
        self.pattern_cache = {}
        self.logger = host.ap.logger.getChild("WeChatReply")
        
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config", "wechat.yaml")
            self._load_config(config_path)
            self._compile_patterns()
            self.logger.info(f"成功加载 {len(self.config['rules'])} 条应答规则")
        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            self.config = {'rules': []}

    def _load_config(self, path):
        """安全加载配置文件"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"配置文件不存在: {path}")
            
        with open(path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f) or {}
            
        # 强制转换配置结构
        if isinstance(config_data, list):
            self.config = {'rules': config_data}
        else:
            self.config = {'rules': config_data.get('rules', [])}

    def _compile_patterns(self):
        """预编译正则表达式（修复空规则问题）"""
        for rule in self.config['rules']:
            try:
                rule_id = rule.get('id', 'unnamed_rule')
                triggers = [str(t).strip() for t in rule.get('triggers', []) if t]
                
                if not triggers:
                    self.logger.warning(f"规则 {rule_id} 无有效触发器，已忽略")
                    continue
                
                self.pattern_cache[rule_id] = [
                    re.compile(pattern, re.IGNORECASE)
                    for pattern in triggers
                ]
            except re.error as e:
                self.logger.error(f"规则 {rule_id} 正则错误: {str(e)}")
            except Exception as e:
                self.logger.error(f"规则 {rule_id} 加载失败: {str(e)}")

    def _get_message_text(self, ctx: EventContext):
        """安全提取消息文本（兼容不同事件类型）"""
        try:
            # 兼容 PersonNormalMessageReceived
            if hasattr(ctx.event, 'text_message'):
                return ctx.event.text_message.strip()
            
            # 兼容 GroupNormalMessageReceived
            if hasattr(ctx.event, 'query') and hasattr(ctx.event.query, 'message_chain'):
                return ''.join(
                    str(p) for p in ctx.event.query.message_chain
                    if isinstance(p, Plain)
                ).strip()
                
            return ""
        except Exception as e:
            self.logger.error(f"消息提取失败: {str(e)}")
            return ""

    def _build_response(self, rule):
        """安全构建响应"""
        try:
            chain = []
            for item in rule.get('response', []):
                if item.get('type') == 'text':
                    content = '\n'.join(line.strip() for line in str(item.get('content', '')).split('\n') if line.strip())
                    if content: 
                        chain.append(Plain(content))
                elif item.get('type') == 'image' and item.get('url'):
                    chain.append(Image(url=item.get('url')))
            return MessageChain(chain) if chain else None
        except Exception as e:
            self.logger.error(f"响应构建失败: {str(e)}")
            return None

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """核心消息处理（修复阻断问题）"""
        try:
            message = self._get_message_text(ctx)
            if not message:
                return
                
            self.logger.debug(f"收到消息: {message[:20]}...")
            
            # 执行匹配
            matched_rule = None
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', message).lower()
            
            for rule in self.config['rules']:
                rule_id = rule.get('id', 'unnamed_rule')
                patterns = self.pattern_cache.get(rule_id, [])
                
                for pattern in patterns:
                    if pattern.search(clean_text):
                        matched_rule = rule
                        break
                if matched_rule:
                    break
                        
            if not matched_rule:
                self.logger.debug("未匹配到规则")
                return
                
            # 构建响应
            response = self._build_response(matched_rule)
            if not response:
                self.logger.warning("构建响应失败")
                return
                
            # 发送并阻断
            ctx.add_return("reply", response)
            ctx.prevent_default()
            self.logger.info(f"已阻断并响应: {message[:15]}...")

        except Exception as e:
            self.logger.error(f"处理异常: {str(e)}")
            ctx.prevent_default()  # 关键修复：异常时也阻断

    def __del__(self):
        self.logger.info("插件已安全卸载")
