"""
LLM Analysis Engine with MCP (Model Context Protocol).

Provides:
    1. MCP Agent mode (requires OpenAI API key) — LLM orchestrates MCP tools
    2. Rule-based fallback — works without any API key

The rule-based engine generates structured insights by analyzing
price spreads, ratings, and value-for-money across all 4 sources.
"""

import json
import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)


async def run_mcp_agent(query: str, api_key: str, model: str = "gpt-4o-mini") -> Optional[dict]:
    """
    Run the LLM MCP Agent.
    Connects to MCP server, uses tools to search all sources, normalize, and rank.
    """
    try:
        from openai import AsyncOpenAI
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        client = AsyncOpenAI(api_key=api_key)

        mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8010")
        if mcp_url.endswith("/"):
            mcp_url = mcp_url[:-1]
        mcp_sse_url = f"{mcp_url}/sse"

        logger.info(f"Connecting to MCP SSE endpoint at {mcp_sse_url}...")

        async with sse_client(mcp_sse_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Get tools from MCP server
                mcp_tools = await session.list_tools()

                # Convert MCP tools to OpenAI format
                openai_tools = []
                for tool in mcp_tools.tools:
                    properties = {}
                    required = []
                    if tool.inputSchema and "properties" in tool.inputSchema:
                        properties = tool.inputSchema["properties"]
                        required = tool.inputSchema.get("required", [])

                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": {
                                "type": "object",
                                "properties": properties,
                                "required": required,
                            }
                        }
                    })

                logger.info(f"Obtained {len(openai_tools)} tools from MCP server.")

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are a shopping AI agent. "
                            "Use the provided tools to search for the product on Amazon, eBay, Google Shopping, and Walmart. "
                            "Then, combine all result JSONs and use the `normalize_data` tool to standardize them. "
                            "Then, pass the normalized data to `rank_products` to get rankings. "
                            "Finally, output a JSON: "
                            '{"insights": "<observations>", "raw_ranked_output": <rank_products JSON>}. '
                            "Output ONLY the JSON string."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Search for '{query}' across Amazon, eBay, Google Shopping, and Walmart. Find the lowest price, normalize, and rank."
                    }
                ]

                # Agent loop
                for i in range(15):
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto"
                    )

                    message = response.choices[0].message
                    messages.append(message)

                    if message.tool_calls:
                        for tool_call in message.tool_calls:
                            try:
                                args = json.loads(tool_call.function.arguments)
                                logger.info(f"LLM executing: {tool_call.function.name}")
                                tool_result = await session.call_tool(tool_call.function.name, args)
                                text_result = "\n".join(
                                    [c.text for c in tool_result.content if getattr(c, "type", "") == "text"]
                                )
                                if len(text_result) > 25000:
                                    text_result = text_result[:25000] + "... [truncated]"
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "content": text_result,
                                })
                            except Exception as e:
                                logger.error(f"Tool failed: {e}")
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.function.name,
                                    "content": f"Error: {e}",
                                })
                    else:
                        final_content = message.content or ""
                        if final_content.startswith("```json"):
                            final_content = final_content[7:-3].strip()
                        elif final_content.startswith("```"):
                            final_content = final_content[3:-3].strip()

                        try:
                            return json.loads(final_content)
                        except json.JSONDecodeError:
                            return {"insights": final_content, "raw_ranked_output": {}}

        return None

    except ImportError:
        logger.warning("OpenAI or MCP package not installed")
        return None
    except Exception as e:
        logger.error(f"MCP Agent failed: {e}")
        return None


def analyze_with_rules(
    query: str,
    products: list[dict],
    best_price: dict,
    best_rating: dict,
    best_value: dict,
) -> str:
    """
    Rule-based analysis engine (works without any API key).
    Generates structured insights by comparing products across all 4 sources.
    """
    insights_parts = []

    if not products:
        return "No products found for your search. Try a different or more specific query."

    # ── Source breakdown ──
    sources = {}
    for p in products:
        src = p.get("source", "Unknown")
        sources[src] = sources.get(src, 0) + 1

    source_summary = ", ".join([f"{src}: {count}" for src, count in sorted(sources.items())])
    insights_parts.append(f"• 📊 Sources: {source_summary}")

    # ── Price spread analysis ──
    prices = [p.get("normalized_price_inr", 0) for p in products if p.get("normalized_price_inr", 0) > 0]
    if prices:
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        spread = max_price - min_price
        spread_pct = (spread / min_price * 100) if min_price > 0 else 0

        insights_parts.append(
            f"• 📈 Price range: ₹{min_price:,.0f} – ₹{max_price:,.0f} "
            f"(avg ₹{avg_price:,.0f}, spread {spread_pct:.0f}%)"
        )

    # ── Best price insight ──
    if best_price:
        insights_parts.append(
            f"• 💰 Cheapest: \"{best_price.get('title', 'N/A')[:60]}\" "
            f"on {best_price.get('source', '?')} at ₹{best_price.get('normalized_price_inr', 0):,.0f}"
        )

    # ── Best rating insight ──
    if best_rating and best_rating.get("rating", 0) > 0:
        insights_parts.append(
            f"• ⭐ Best rated: \"{best_rating.get('title', 'N/A')[:60]}\" "
            f"on {best_rating.get('source', '?')} — {best_rating.get('rating', 0)}/5 "
            f"({best_rating.get('reviews', 0):,} reviews)"
        )

    # ── Savings opportunity ──
    if best_price and best_rating:
        bp_price = best_price.get("normalized_price_inr", 0)
        br_price = best_rating.get("normalized_price_inr", 0)
        if bp_price < br_price and bp_price > 0:
            savings = br_price - bp_price
            insights_parts.append(
                f"• 💡 Save ₹{savings:,.0f} by choosing the cheapest over the highest-rated option"
            )

    # ── Cross-platform comparison ──
    if len(sources) > 1:
        insights_parts.append(
            f"• 🌐 Compared across {len(sources)} platforms for the best deal"
        )

    return "\n".join(insights_parts) if insights_parts else "Analysis complete. See product comparison above."
