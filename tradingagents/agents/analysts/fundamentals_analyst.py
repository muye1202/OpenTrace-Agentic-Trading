from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement, get_insider_sentiment, get_insider_transactions
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]
        portfolio_context = state.get("portfolio_context", "")

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_insider_sentiment,
            get_insider_transactions,
        ]

        system_message = (
            "You are a fundamentals analyst supporting a short-term (1–2 month) swing trade decision. Focus on what can plausibly matter over the next 4–8 weeks (quality, liquidity/financing risk, earnings sensitivity, and any near-term fundamental catalysts)."
            "\n\nWorkflow (tool-first, then write):"
            "\n1) Call `get_fundamentals(ticker=<ticker>, curr_date=<current_date>)` to pull the company overview/ratios."
            "\n2) Call `get_income_statement`, `get_balance_sheet`, and `get_cashflow` (quarterly) to identify recent acceleration/deceleration and balance-sheet constraints."
            "\n3) Call `get_insider_transactions` and `get_insider_sentiment` if available; if a vendor/tool returns missing data, note it and proceed."
            "\n4) Write the final report **without** further tool calls."
            "\n\nReport requirements (keep it to-the-point and trade-relevant):"
            "\n- Near-term fundamental narrative: what changed recently and what could change next (don’t invent dates)."
            "\n- Earnings sensitivity: which line items/segments/margins matter most; what the market is likely keying on."
            "\n- Balance-sheet/liquidity: cash, debt, liquidity runway, refinancing risk (if discernible)."
            "\n- Valuation/expectations: whether expectations look stretched vs recent fundamentals (use available ratios; avoid long debates)."
            "\n- Insider activity: summarize net buying/selling and any notable patterns."
            "\n- Bottom line: bullish/bearish fundamental bias for a 1–2 month horizon + 2–3 concrete risks that would invalidate it."
            "\n\nEnd with a compact Markdown table summarizing: key metric(s), directionality, why it matters in 4–8 weeks, and the risk if wrong."
        )

        if portfolio_context:
            system_message += (
                "\n\n---\nCURRENT PORTFOLIO CONTEXT (live brokerage snapshot):\n"
                + str(portfolio_context)
                + "\n\nExecution note: The system can place MARKET (execute now) or conditional orders (LIMIT/STOP/STOP_LIMIT/TRAILING_STOP) that may execute later. Highlight any near-term catalysts/risks that would affect whether to execute now vs stage entries/exits.\n---"
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
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
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
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
