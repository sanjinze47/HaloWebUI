import { describe, expect, it } from 'vitest';

import {
	attachResponseTaskId,
	beginResponseTask,
	finishResponseTask,
	getResponseTaskIds,
	hasPendingResponses,
	restoreResponseTasks,
	shouldTrackResponseTaskForChat,
	shouldShowResponseStopControl
} from './chat-task-registry';

describe('chat task registry', () => {
	it('removes only the completed response task', () => {
		let registry = beginResponseTask({}, 'response-a');
		registry = beginResponseTask(registry, 'response-b');
		registry = attachResponseTaskId(registry, 'response-a', 'task-a');
		registry = attachResponseTaskId(registry, 'response-b', 'task-b');

		registry = finishResponseTask(registry, 'response-a');

		expect(registry).toEqual({
			'response-b': { phase: 'running', taskId: 'task-b' }
		});
		expect(getResponseTaskIds(registry)).toEqual(['task-b']);
		expect(hasPendingResponses(registry)).toBe(true);
	});

	it('does not resurrect a response completed before its task id arrived', () => {
		let registry = beginResponseTask({}, 'response-a');
		registry = finishResponseTask(registry, 'response-a');
		registry = attachResponseTaskId(registry, 'response-a', 'task-a');

		expect(registry).toEqual({});
	});

	it('restores message mappings from chat context metadata', () => {
		expect(
			restoreResponseTasks([
				{ task_id: 'task-a', message_id: 'response-a' },
				{ task_id: 'task-b', message_id: 'response-b' }
			])
		).toEqual({
			'response-a': { phase: 'running', taskId: 'task-a' },
			'response-b': { phase: 'running', taskId: 'task-b' }
		});
	});

	it('does not attach a delayed task id after navigating to another chat', () => {
		expect(shouldTrackResponseTaskForChat('chat-b', 'chat-a')).toBe(false);
		expect(shouldTrackResponseTaskForChat('chat-a', 'chat-a')).toBe(true);
	});

	it('keeps the stop control available while a sibling is waiting for its task id', () => {
		expect(
			shouldShowResponseStopControl({
				taskIds: null,
				hasPendingResponseTasks: true,
				currentMessageDone: true
			})
		).toBe(true);
	});
});
