from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

# 注册插件（必须放在类定义前）
@register(
    name="WeChatReply",
    description="微信关键词回复插件",
    version="1.0",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """微信关键词回复插件"""
    
    def __init__(self, host: APIHost):
        # 初始化配置
        self.config = None
        self._load_config()
        self._init_logger(host)
        
        # 预编译正则表达式提升性能
        self.pattern_cache = {}
        
    async def initialize(self):
        """异步初始化资源"""
        self.ap.logger.info("BusinessReply 插件初始化完成")

    def _init_logger(self, host):
        """初始化日志系统"""
        self.logger = host.ap.logger.getChild("BusinessReply")
        self.logger.setLevel("DEBUG")

    def _load_config(self):
        """加载配置文件"""
        config_path = os.path.join(
            os.path.dirname(__file__), 
            "config/wechat.yaml"
        )
        
        # 配置文件校验
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件未找到: {config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.logger.debug(f"已加载 {len(self.config['rules'])} 条应答规则")

    def _build_response(self, rule):
        """构建消息链"""
        chain = []
        for item in rule['response']:
            if item['type'] == 'text':
                content = '\n'.join(line.strip() for line in item['content'].split('\n'))
                chain.append(Plain(content))
            elif item['type'] == 'image':
                chain.append(Image(url=item['url']))
        return MessageChain(chain)

    def _match_rule(self, message):
        """高级匹配逻辑"""
        clean_msg = re.sub(r'[^\w\u4e00-\u9fff]', '', message).lower()
        
        for rule in self.config['rules']:
            # 缓存正则表达式
            patterns = self.pattern_cache.get(rule['id'], [
                re.compile(pattern, re.IGNORECASE) 
                for pattern in rule['triggers']
            ])
            
            for pattern in patterns:
                if pattern.search(clean_msg):
                    return rule
        return None

    @handler(PersonNormalMessageReceived, priority=100)
    async def handle_private(self, ctx: EventContext):
        """处理私聊消息"""
        await self._process_message(ctx)

    @handler(GroupNormalMessageReceived, priority=100)
    async def handle_group(self, ctx: EventContext):
        """处理群聊消息"""
        await self._process_message(ctx)

    async def _process_message(self, ctx):
        """统一处理消息"""
        message = ''.join(
            str(p) for p in ctx.event.message_chain 
            if isinstance(p, Plain)
        ).strip()
        
        # 执行深度匹配
        matched_rule = self._match_rule(message)
        
        if matched_rule:
            # 构建响应
            response = self._build_response(matched_rule)
            
            # 添加响应并阻止默认行为
            ctx.add_return("reply", response)
            ctx.prevent_default()
            
            self.logger.info(f"已响应消息: {message[:20]}...")

    def __del__(self):
        """资源清理"""
        self.logger.info("插件已卸载")
