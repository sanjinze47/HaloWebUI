export const applyFailedResponseToHistory = <
	History extends { messages?: Record<string, any> },
	Response extends { id: string }
>(
	history: History,
	response: Response
) => ({
	...history,
	messages: {
		...(history.messages ?? {}),
		[response.id]: {
			...(history.messages?.[response.id] ?? {}),
			...response
		}
	}
});

export const buildFailedResponseChatPayload = <
	Payload extends { history?: any; messages?: any[] },
	History extends { messages?: Record<string, any> },
	Response extends { id: string }
>(
	payload: Payload,
	history: History,
	response: Response
) => {
	const nextHistory = applyFailedResponseToHistory(history, response);
	const messages = [...(payload.messages ?? [])];
	const messageIndex = messages.findIndex((message) => message?.id === response.id);
	if (messageIndex >= 0) {
		messages[messageIndex] = { ...messages[messageIndex], ...response };
	} else {
		messages.push(response);
	}

	return {
		...payload,
		history: nextHistory,
		messages
	};
};
