# plugins/WeChatReply/main.py
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词自动应答系统",
    version="2.1",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """企业级关键词应答解决方案"""
    
    def __init__(self, host: APIHost):
        self.host = host
        self.config = {'rules': []}
        self.pattern_cache = {}
        self.logger = host.ap.logger.getChild("WeChatReply")
        
        try:
            # 加载配置文件
            config_path = os.path.join(
                os.path.dirname(__file__), 
                "config", 
                "wechat.yaml"
            )
            
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

    def _build_response(self, rule):
        """安全构建响应消息"""
        try:
            chain = []
            for item in rule.get('response', []):
                if item['type'] == 'text':
                    content = '\n'.join(
                        line.strip() 
                        for line in str(item.get('content', '')).split('\n') 
                        if line.strip()
                    )
                    if content:
                        chain.append(Plain(content))
                elif item['type'] == 'image':
                    if url := item.get('url'):
                        chain.append(Image(url=url))
            return MessageChain(chain) if chain else None
        except Exception as e:
            self.logger.error(f"构建响应失败: {str(e)}")
            return None

    def _match_message(self, text):
        """执行消息匹配"""
        try:
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', text).strip()
            if not clean_text:
                return None
                
            for rule in self.config['rules']:
                for pattern in self.pattern_cache.get(rule['id'], []):
                    if pattern.search(clean_text):
                        return rule
            return None
        except Exception as e:
            self.logger.error(f"匹配过程异常: {str(e)}")
            return None

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """统一消息处理入口"""
        try:
            # 提取纯文本内容
            message = ''.join(
                str(p) for p in ctx.event.message_chain 
                if isinstance(p, Plain)
            ).strip()
            
            if not message:
                return
                
            # 执行匹配
            matched_rule = self._match_message(message)
            if not matched_rule:
                return
                
            # 构建响应
            if response := self._build_response(matched_rule):
                ctx.add_return("reply", response)
                ctx.prevent_default()
                self.logger.info(f"已响应: {message[:15]}...")

        except Exception as e:
            self.logger.error(f"处理消息异常: {str(e)}")

    def __del__(self):
        self.logger.info("插件已安全卸载")
