from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupNormalMessageReceived
from pkg.platform.types import MessageChain, Plain, Image
import yaml
import os
import re

@register(
    name="WeChatReply",
    description="微信关键词回复插件",
    version="4.1",
    author="xiaoxin",
)
class WeChatReplyPlugin(BasePlugin):
    """最终修复版本"""
    
    def __init__(self, host: APIHost):
        self.host = host
        self.config = {'rules': []}
        self.pattern_cache = {}
        self.logger = host.ap.logger.getChild("WeChatReply")
        
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config", "wechat.yaml")
            self._load_config(config_path)
            self._compile_patterns()
            self.logger.info(f"成功加载 {len(self.config['rules'])} 条回复规则")
            self.logger.debug(f"已编译正则: {self.pattern_cache}")  # 新增调试日志
        except Exception as e:
            self.logger.error(f"初始化失败: {str(e)}")
            self.config = {'rules': []}

    def _load_config(self, path):
        """安全加载配置"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
                
            # 结构转换
            if isinstance(raw_data, list):
                self.config = {'rules': raw_data}
            elif isinstance(raw_data, dict):
                self.config = {'rules': raw_data.get('rules', [])}
            else:
                self.config = {'rules': []}
                
            self.logger.debug(f"原始配置内容: {raw_data}")  # 新增调试日志
                
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
                    self.logger.warning(f"规则 {rule_id} 无有效触发器，已忽略")
                    continue
                
                compiled = []
                for pattern in triggers:
                    try:
                        compiled.append(re.compile(pattern, re.IGNORECASE))
                    except re.error as e:
                        self.logger.error(f"规则 {rule_id} 正则错误 '{pattern}': {str(e)}")
                self.pattern_cache[rule_id] = compiled
                
            except Exception as e:
                self.logger.error(f"规则 {rule_id} 加载失败: {str(e)}")

    def _get_message_text(self, ctx: EventContext):
        """消息提取（增强兼容性）"""
        try:
            # 新版事件结构
            if hasattr(ctx.event, 'query') and hasattr(ctx.event.query, 'message_chain'):
                text = ''.join(
                    str(p) for p in ctx.event.query.message_chain
                    if isinstance(p, Plain)
                ).strip()
                self.logger.debug(f"从query.message_chain提取消息: {text}")  # 新增调试
                return text
            # 旧版事件结构
            elif hasattr(ctx.event, 'text_message'):
                text = ctx.event.text_message.strip()
                self.logger.debug(f"从text_message提取消息: {text}")
                return text
            return ""
        except Exception as e:
            self.logger.error(f"消息提取失败: {str(e)}")
            return ""

    @handler(PersonNormalMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def handle_message(self, ctx: EventContext):
        """核心处理逻辑（增强日志）"""
        try:
            message = self._get_message_text(ctx)
            if not message:
                self.logger.debug("收到空消息，已忽略")
                return
                
            self.logger.debug(f"原始消息内容: {message}")
            
            clean_text = re.sub(r'[^\w\u4e00-\u9fff]', '', message).lower()
            self.logger.debug(f"清洗后文本: {clean_text}")
            
            matched_rule = None
            
            # 安全遍历规则
            for rule in self.config.get('rules', []):
                rule_id = rule.get('id', 'unnamed')
                patterns = self.pattern_cache.get(rule_id, [])
                self.logger.debug(f"检查规则 {rule_id}，共有{len(patterns)}个正则")
                
                for pattern in patterns:
                    if pattern.search(clean_text):
                        matched_rule = rule
                        self.logger.info(f"匹配成功: 规则 {rule_id} 触发词 {pattern.pattern}")
                        break
                if matched_rule:
                    break
                        
            if not matched_rule:
                self.logger.debug("未匹配到任何规则")
                return
                
            # 构建响应
            response = self._build_response(matched_rule)
            if response:
                ctx.add_return("reply", response)
                ctx.prevent_default()
                self.logger.info(f"已发送响应并阻断默认行为")
            else:
                self.logger.warning("构建响应失败，已阻断默认行为")
                ctx.prevent_default()

        except Exception as e:
            self.logger.error(f"处理异常: {str(e)}")
            ctx.prevent_default()

    def _build_response(self, rule):
        """响应构建（带严格校验）"""
        try:
            chain = []
            for item in rule.get('response', []):
                if item.get('type') == 'text':
                    content = '\n'.join(line.strip() for line in str(item.get('content', '')).split('\n') if line.strip())
                    if content: 
                        chain.append(Plain(content))
                        self.logger.debug(f"添加文本响应: {content[:20]}...")
                elif item.get('type') == 'image' and item.get('url'):
                    url = item.get('url')
                    chain.append(Image(url=url))
                    self.logger.debug(f"添加图片响应: {url}")
            return MessageChain(chain) if chain else None
        except Exception as e:
            self.logger.error(f"响应构建失败: {str(e)}")
            return None

    def __del__(self):
        self.logger.info("插件已卸载")
