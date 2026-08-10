export type ResponseTaskPhase = 'requesting' | 'running';

export type ResponseTask = {
	taskId?: string;
	phase: ResponseTaskPhase;
};

export type ResponseTaskRegistry = Record<string, ResponseTask>;

export type ChatContextTask = {
	task_id: string;
	message_id: string;
};

export const beginResponseTask = (
	registry: ResponseTaskRegistry,
	messageId: string
): ResponseTaskRegistry => ({
	...registry,
	[messageId]: { phase: 'requesting' }
});

export const attachResponseTaskId = (
	registry: ResponseTaskRegistry,
	messageId: string,
	taskId: string
): ResponseTaskRegistry => {
	if (!registry[messageId] || !taskId) {
		return registry;
	}

	return {
		...registry,
		[messageId]: { phase: 'running', taskId }
	};
};

export const finishResponseTask = (
	registry: ResponseTaskRegistry,
	messageId: string
): ResponseTaskRegistry => {
	if (!registry[messageId]) {
		return registry;
	}

	const next = { ...registry };
	delete next[messageId];
	return next;
};

export const restoreResponseTasks = (tasks: ChatContextTask[] | null | undefined) => {
	const registry: ResponseTaskRegistry = {};
	for (const task of tasks ?? []) {
		if (task?.task_id && task?.message_id) {
			registry[task.message_id] = { phase: 'running', taskId: task.task_id };
		}
	}
	return registry;
};

export const getResponseTaskIds = (registry: ResponseTaskRegistry) =>
	Object.values(registry)
		.map((task) => task.taskId)
		.filter((taskId): taskId is string => Boolean(taskId));

export const hasPendingResponses = (registry: ResponseTaskRegistry) =>
	Object.keys(registry).length > 0;

export const shouldTrackResponseTaskForChat = (
	currentChatId: string | null | undefined,
	requestChatId: string | null | undefined
) => Boolean(currentChatId && requestChatId && currentChatId === requestChatId);

export const shouldShowResponseStopControl = ({
	taskIds,
	hasPendingResponseTasks,
	currentMessageDone
}: {
	taskIds: string[] | null | undefined;
	hasPendingResponseTasks: boolean;
	currentMessageDone: boolean | null | undefined;
}) => hasPendingResponseTasks || Boolean(taskIds?.length) || currentMessageDone !== true;
