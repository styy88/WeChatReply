from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
from pkg.platform.types import *

class WeChatReplyPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        # 加载配置
        self.keyword_actions = self.config.get("keyword_actions", [])
        
    async def initialize(self):
        self.ap.logger.info("微信关键词回复插件初始化完成")

    # 统一消息处理
    async def process_message(self, ctx: EventContext, is_group: bool):
        msg = ctx.event.text_message.strip()
        sender_id = ctx.event.sender_id
        
        # 遍历配置的关键词
        for action in self.keyword_actions:
            if msg == action["keyword"]:
                # 执行对应动作
                if action["type"] == "text":
                    reply = [Plain(action["content"])]
                elif action["type"] == "quote":
                    reply = self.build_quote_reply(ctx, action["content"])
                elif action["type"] == "forward":
                    reply = self.build_forward_reply(ctx, action["content"])
                
                # 添加回复
                ctx.add_return("reply", reply)
                ctx.prevent_default()
                self.ap.logger.info(f"已响应 {sender_id} 的消息：{msg}")
                break

    # 构建引用回复
    def build_quote_reply(self, ctx: EventContext, content: str):
        return MessageChain([
            Quote(
                id=ctx.event.message_id,
                sender_id=ctx.event.sender_id,
                origin=ctx.event.message_chain
            ),
            Plain(content)
        ])

    # 构建转发回复
    def build_forward_reply(self, ctx: EventContext, content: str):
        return MessageChain([
            Forward(
                display=ForwardMessageDiaplay(
                    title="重要消息转发",
                    preview=[content[:20]]
                ),
                node_list=[
                    ForwardMessageNode(
                        sender_id=ctx.event.sender_id,
                        sender_name="系统通知",
                        message_chain=MessageChain([Plain(content)]),
                        time=datetime.now()
                    )
                ]
            )
        ])

    @handler(PersonNormalMessageReceived)
    async def person_message(self, ctx: EventContext):
        await self.process_message(ctx, False)

    @handler(GroupNormalMessageReceived)
    async def group_message(self, ctx: EventContext):
        await self.process_message(ctx, True)

    def __del__(self):
        self.ap.logger.info("微信关键词回复插件已卸载")
