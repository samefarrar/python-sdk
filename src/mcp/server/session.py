from enum import Enum
from typing import Any

import anyio
import anyio.lowlevel
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import AnyUrl

import mcp.types as types
from mcp.server.models import InitializationOptions
from mcp.shared.session import (
    BaseSession,
    RequestResponder,
)


class InitializationState(Enum):
    NotInitialized = 1
    Initializing = 2
    Initialized = 3


class ServerSession(
    BaseSession[
        types.ServerRequest,
        types.ServerNotification,
        types.ServerResult,
        types.ClientRequest,
        types.ClientNotification,
    ]
):
    _initialized: InitializationState = InitializationState.NotInitialized

    def __init__(
        self,
        read_stream: MemoryObjectReceiveStream[types.JSONRPCMessage | Exception],
        write_stream: MemoryObjectSendStream[types.JSONRPCMessage],
        init_options: InitializationOptions,
    ) -> None:
        super().__init__(
            read_stream, write_stream, types.ClientRequest, types.ClientNotification
        )
        self._initialization_state = InitializationState.NotInitialized
        self._init_options = init_options

    async def _received_request(
        self, responder: RequestResponder[types.ClientRequest, types.ServerResult]
    ):
        match responder.request.root:
            case types.InitializeRequest():
                self._initialization_state = InitializationState.Initializing
                await responder.respond(
                    types.ServerResult(
                        types.InitializeResult(
                            protocolVersion=types.LATEST_PROTOCOL_VERSION,
                            capabilities=self._init_options.capabilities,
                            serverInfo=types.Implementation(
                                name=self._init_options.server_name,
                                version=self._init_options.server_version,
                            ),
                        )
                    )
                )
            case _:
                if self._initialization_state != InitializationState.Initialized:
                    raise RuntimeError(
                        "Received request before initialization was complete"
                    )

    async def _received_notification(
        self, notification: types.ClientNotification
    ) -> None:
        # Need this to avoid ASYNC910
        await anyio.lowlevel.checkpoint()
        match notification.root:
            case types.InitializedNotification():
                self._initialization_state = InitializationState.Initialized
            case _:
                if self._initialization_state != InitializationState.Initialized:
                    raise RuntimeError(
                        "Received notification before initialization was complete"
                    )

    async def send_log_message(
        self, level: types.LoggingLevel, data: Any, logger: str | None = None
    ) -> None:
        """Send a log message notification."""
        await self.send_notification(
            types.ServerNotification(
                types.LoggingMessageNotification(
                    method="notifications/message",
                    params=types.LoggingMessageNotificationParams(
                        level=level,
                        data=data,
                        logger=logger,
                    ),
                )
            )
        )

    async def send_resource_updated(self, uri: AnyUrl) -> None:
        """Send a resource updated notification."""
        await self.send_notification(
            types.ServerNotification(
                types.ResourceUpdatedNotification(
                    method="notifications/resources/updated",
                    params=types.ResourceUpdatedNotificationParams(uri=uri),
                )
            )
        )

    async def create_message(
        self,
        messages: list[types.SamplingMessage],
        *,
        max_tokens: int,
        system_prompt: str | None = None,
        include_context: types.IncludeContext | None = None,
        temperature: float | None = None,
        stop_sequences: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        model_preferences: types.ModelPreferences | None = None,
    ) -> types.CreateMessageResult:
        """Send a sampling/create_message request."""
        return await self.send_request(
            types.ServerRequest(
                types.CreateMessageRequest(
                    method="sampling/createMessage",
                    params=types.CreateMessageRequestParams(
                        messages=messages,
                        systemPrompt=system_prompt,
                        includeContext=include_context,
                        temperature=temperature,
                        maxTokens=max_tokens,
                        stopSequences=stop_sequences,
                        metadata=metadata,
                        modelPreferences=model_preferences,
                    ),
                )
            ),
            types.CreateMessageResult,
        )

    async def list_roots(self) -> types.ListRootsResult:
        """Send a roots/list request."""
        return await self.send_request(
            types.ServerRequest(
                types.ListRootsRequest(
                    method="roots/list",
                )
            ),
            types.ListRootsResult,
        )

    async def send_ping(self) -> types.EmptyResult:
        """Send a ping request."""
        return await self.send_request(
            types.ServerRequest(
                types.PingRequest(
                    method="ping",
                )
            ),
            types.EmptyResult,
        )

    async def send_progress_notification(
        self, progress_token: str | int, progress: float, total: float | None = None
    ) -> None:
        """Send a progress notification."""
        await self.send_notification(
            types.ServerNotification(
                types.ProgressNotification(
                    method="notifications/progress",
                    params=types.ProgressNotificationParams(
                        progressToken=progress_token,
                        progress=progress,
                        total=total,
                    ),
                )
            )
        )

    async def send_resource_list_changed(self) -> None:
        """Send a resource list changed notification."""
        await self.send_notification(
            types.ServerNotification(
                types.ResourceListChangedNotification(
                    method="notifications/resources/list_changed",
                )
            )
        )

    async def send_tool_list_changed(self) -> None:
        """Send a tool list changed notification."""
        await self.send_notification(
            types.ServerNotification(
                types.ToolListChangedNotification(
                    method="notifications/tools/list_changed",
                )
            )
        )

    async def send_prompt_list_changed(self) -> None:
        """Send a prompt list changed notification."""
        await self.send_notification(
            types.ServerNotification(
                types.PromptListChangedNotification(
                    method="notifications/prompts/list_changed",
                )
            )
        )