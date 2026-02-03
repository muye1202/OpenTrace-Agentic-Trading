from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_news, get_company_news_window, get_global_news
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        portfolio_context = state.get("portfolio_context", "")

        tools = [
            get_news,
            get_company_news_window,
            get_global_news,
        ]

        system_message = (
            "You are a news + macro analyst supporting a short-term (1–2 month) swing trade decision. Your job is to identify *trade-relevant* catalysts and risks for the next 4–8 weeks, not to produce a long general news recap."
            "\n\nWorkflow (tool-first, then write):"
            "\n1) Pull company-specific news/sentiment for the last ~21 days using `get_company_news_window(ticker=<ticker>, curr_date=<current_date>, look_back_days=21)` (fallback: `get_news`)."
            "\n2) Pull macro/regime headlines using `get_global_news(curr_date=<current_date>, look_back_days=7, limit=10)`."
            "\n3) After you have data, write the final report **without** further tool calls."
            "\n\nReport requirements (to-the-point, trading oriented):"
            "\n- Company catalysts: summarize key storylines; map each to likely price impact direction and time window."
            "\n- Macro/regime: risk-on/off tone, rates/inflation themes, and how they could affect the ticker/sector."
            "\n- Sentiment/positioning signals from the vendor output (e.g., Alpha Vantage news sentiment scores) if present."
            "\n- Event-driven risk: list 3–5 plausible upcoming catalysts/risks over the next 4–8 weeks (don’t invent dates; describe them generically if unknown)."
            "\n- Bottom line: short-term news-driven bias (bullish/bearish/neutral) + what headline would invalidate it."
            "\n\nEnd with a compact Markdown table: theme, bullish/bearish impulse, confidence, time horizon, and key watch item."
        )

        if portfolio_context:
            system_message += (
                "\n\n---\nCURRENT PORTFOLIO CONTEXT (live brokerage snapshot):\n"
                + str(portfolio_context)
                + "\n\nExecution note: The system can place MARKET (execute now) or conditional orders (LIMIT/STOP/STOP_LIMIT/TRAILING_STOP) that may execute later. Call out catalyst timing that favors immediate execution vs staged/conditional orders.\n---"
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. We are looking at the company {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
