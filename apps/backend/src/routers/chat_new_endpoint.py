"""
Refactored POST /chat endpoint using Design Patterns.

This is the new, clean implementation that will replace the old one.
"""


@router.post("/chat", tags=["chat"])
async def send_chat_message(
    request: ChatRequest,
    http_request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Send a chat message and get AI response.

    Refactored using:
    - ChatContext dataclass for type-safe request encapsulation
    - Strategy Pattern for pluggable chat handlers
    - Builder Pattern for declarative response construction

    Handles both new conversations and continuing existing ones.
    """

    start_time = time.time()
    response.headers.update(NO_STORE_HEADERS)
    user_id = getattr(http_request.state, "user_id", "mock-user-id")

    try:
        # 1. Build immutable context from request
        context = _build_chat_context(request, user_id, settings)

        logger.info(
            "Processing chat request",
            request_id=context.request_id,
            user_id=context.user_id,
            model=context.model,
            kill_switch=context.kill_switch_active,
        )

        # 2. Initialize services
        chat_service = ChatService(settings)
        cache = await get_redis_cache()

        # 3. Get or create session
        chat_session = await chat_service.get_or_create_session(
            chat_id=context.chat_id,
            user_id=context.user_id,
            first_message=context.message,
            tools_enabled=context.tools_enabled,
        )

        # Update context with resolved session
        context = context.with_session(chat_session.id)

        # 4. Add user message
        user_message = await chat_service.add_user_message(
            chat_session=chat_session, content=context.message
        )

        # 5. Select and execute appropriate strategy
        async with trace_span(
            "chat_strategy_execution",
            {
                "strategy": "simple" if context.kill_switch_active else "coordinated",
                "session_id": context.session_id,
            },
        ):
            # ADR-001: Direct instantiation (factory removed - YAGNI)
            strategy = SimpleChatStrategy(chat_service)
            result = await strategy.process(context)

        # 6. Save assistant message
        assistant_message = await chat_service.add_assistant_message(
            chat_session=chat_session,
            content=result.sanitized_content,
            model=result.metadata.model_used,
            task_id=result.task_id,
            metadata=result.metadata.decision_metadata or {},
            tokens=(
                result.metadata.tokens_used.get("total")
                if result.metadata.tokens_used
                else None
            ),
            latency_ms=(
                int(result.metadata.latency_ms) if result.metadata.latency_ms else None
            ),
        )

        # Update result with message IDs
        result.metadata.user_message_id = user_message.id
        result.metadata.assistant_message_id = assistant_message.id

        # 7. Invalidate caches
        await cache.invalidate_chat_history(chat_session.id)
        if result.research_triggered:
            await cache.invalidate_research_tasks(chat_session.id)

        # 8. Build and return response using Builder Pattern
        return (
            ChatResponseBuilder()
            .from_processing_result(result)
            .with_metadata("processing_time_ms", (time.time() - start_time) * 1000)
            .build()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing chat message",
            error=str(e),
            user_id=user_id,
            exc_info=True,
        )

        return (
            ChatResponseBuilder()
            .with_error(f"Failed to process message: {str(e)}")
            .with_metadata("user_id", user_id)
            .build_error(status_code=500)
        )
