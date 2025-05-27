from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词回复插件",
    version="1.1",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """修复版微信关键词自动应答插件"""
    
    def __init__(self, host: APIHost):
        # 初始化必要属性
        self.host = host
        self.config = None
        self.pattern_cache = {}
        
        # 初始化日志系统
        self.logger = host.ap.logger.getChild("WeChatReply")
        self.logger.setLevel("DEBUG")
        
        # 加载配置文件
        try:
            config_path = os.path.join(
                os.path.dirname(__file__), 
                "config", 
                "wechat.yaml"
            )
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"配置文件未找到: {config_path}")
                
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
                self.logger.info(f"成功加载 {len(self.config['rules'])} 条应答规则")
                
            # 预编译正则表达式
            for rule in self.config['rules']:
                self.pattern_cache[rule['id']] = [
                    re.compile(pattern, re.IGNORECASE) 
                    for pattern in rule['triggers']
                ]
                
        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            self.config = {'rules': []}  # 安全降级

    async def initialize(self):
        """异步初始化"""
        self.logger.debug("插件初始化完成")

    def _build_response(self, rule):
        """安全构建响应消息链"""
        try:
            chain = []
            for item in rule['response']:
                if item['type'] == 'text':
                    # 清理文本内容中的多余空格
                    content = '\n'.join(
                        line.strip() 
                        for line in item['content'].split('\n')
                        if line.strip()
                    )
                    chain.append(Plain(content))
                elif item['type'] == 'image':
                    if 'url' in item:
                        chain.append(Image(url=item['url']))
                    else:
                        self.logger.warning(f"规则 {rule['id']} 图片配置不完整")
            return MessageChain(chain)
        except Exception as e:
            self.logger.error(f"构建响应失败: {str(e)}")
            return MessageChain([Plain("服务暂时不可用，请稍后再试")])

    def _match_message(self, text):
        """执行消息匹配"""
        try:
            # 清理非中文字符和标点
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', text).lower()
            
            for rule in self.config['rules']:
                patterns = self.pattern_cache.get(rule['id'], [])
                for pattern in patterns:
                    if pattern.search(clean_text):
                        return rule
            return None
        except Exception as e:
            self.logger.error(f"匹配过程出错: {str(e)}")
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
            
            if matched_rule:
                # 构建并发送响应
                response = self._build_response(matched_rule)
                ctx.add_return("reply", response)
                ctx.prevent_default()
                self.logger.info(f"已响应消息: {message[:15]}...")

        except Exception as e:
            self.logger.error(f"消息处理异常: {str(e)}")

    def __del__(self):
        """资源清理"""
        self.logger.info("插件卸载完成")
