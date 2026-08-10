import { describe, expect, it } from 'vitest';

import {
	applyFailedResponseToHistory,
	buildFailedResponseChatPayload
} from './chat-response-failure';

describe('chat response failure state', () => {
	it('updates the originating history without mutating the currently displayed chat', () => {
		const originHistory = {
			currentId: 'response-a',
			messages: { 'response-a': { id: 'response-a', done: false } }
		};
		const currentHistory = {
			currentId: 'message-b',
			messages: { 'message-b': { id: 'message-b', content: 'chat b' } }
		};
		const failure = { id: 'response-a', done: true, error: { content: 'failed' } };

		const nextOriginHistory = applyFailedResponseToHistory(originHistory, failure);

		expect(nextOriginHistory.messages['response-a']).toMatchObject(failure);
		expect(currentHistory).toEqual({
			currentId: 'message-b',
			messages: { 'message-b': { id: 'message-b', content: 'chat b' } }
		});
	});

	it('builds a scoped payload that persists the failed response in its original chat', () => {
		const failure = { id: 'response-a', done: true, error: { content: 'failed' } };
		const payload = buildFailedResponseChatPayload(
			{
				history: {},
				messages: [{ id: 'response-a', done: false }],
				params: { temperature: 0.2 }
			},
			{
				currentId: 'response-a',
				messages: { 'response-a': { id: 'response-a', done: false } }
			},
			failure
		);

		expect(payload.history.messages['response-a']).toMatchObject(failure);
		expect(payload.messages).toEqual([expect.objectContaining(failure)]);
		expect(payload.params).toEqual({ temperature: 0.2 });
	});
});
