from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词回复插件",
    version="4.0",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """最终修复版"""
    
    def __init__(self, host: APIHost):
        self.host = host
        self.config = {'rules': []}  # 确保默认结构
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
        """安全加载配置（强制结构转换）"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
                
            # 结构转换
            if isinstance(raw_data, list):
                self.config = {'rules': raw_data}
            elif 'rules' in raw_data:
                self.config = {'rules': raw_data['rules']}
            else:
                self.config = {'rules': []}
                
        except Exception as e:
            self.logger.error(f"配置解析失败: {str(e)}")
            self.config = {'rules': []}

    def _compile_patterns(self):
        """正则预编译（带安全校验）"""
        for rule in self.config.get('rules', []):
            try:
                rule_id = rule.get('id', str(id(rule)))
                triggers = [str(t) for t in rule.get('triggers', []) if t]
                
                if not triggers:
                    self.logger.warning(f"规则 {rule_id} 无有效触发器")
                    continue
                
                self.pattern_cache[rule_id] = [
                    re.compile(pattern.strip(), re.IGNORECASE)
                    for pattern in triggers
                ]
            except Exception as e:
                self.logger.error(f"规则 {rule_id} 加载失败: {str(e)}")

    def _get_message_text(self, ctx: EventContext):
        """消息提取（兼容新旧事件结构）"""
        try:
            # 新版事件结构
            if hasattr(ctx.event, 'query') and hasattr(ctx.event.query, 'message_chain'):
                return ''.join(
                    str(p) for p in ctx.event.query.message_chain
                    if isinstance(p, Plain)
                ).strip()
            # 旧版事件结构
            elif hasattr(ctx.event, 'text_message'):
                return ctx.event.text_message.strip()
            return ""
        except Exception as e:
            self.logger.error(f"消息提取失败: {str(e)}")
            return ""

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """核心处理逻辑"""
        try:
            message = self._get_message_text(ctx)
            if not message:
                return
                
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', message).lower()
            matched_rule = None
            
            # 安全遍历规则
            for rule in self.config.get('rules', []):
                patterns = self.pattern_cache.get(rule.get('id', ''), [])
                for pattern in patterns:
                    if pattern.search(clean_text):
                        matched_rule = rule
                        break
                if matched_rule:
                    break
                        
            if not matched_rule:
                return
                
            # 构建响应
            response = self._build_response(matched_rule)
            if response:
                ctx.add_return("reply", response)
                ctx.prevent_default()
                self.logger.info(f"已响应: {message[:15]}...")

        except Exception as e:
            self.logger.error(f"处理异常: {str(e)}")
            ctx.prevent_default()

    def _build_response(self, rule):
        """响应构建（带空值校验）"""
        try:
            chain = []
            for item in rule.get('response', []):
                if item.get('type') == 'text':
                    content = '\n'.join(line.strip() for line in str(item.get('content', '')).split('\n') if line.strip())
                    if content: chain.append(Plain(content))
                elif item.get('type') == 'image' and item.get('url'):
                    chain.append(Image(url=item.get('url')))
            return MessageChain(chain) if chain else None
        except Exception as e:
            self.logger.error(f"响应构建失败: {str(e)}")
            return None

    def __del__(self):
        self.logger.info("插件已卸载")
