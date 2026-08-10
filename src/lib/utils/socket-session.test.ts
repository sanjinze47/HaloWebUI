import { describe, expect, it, vi } from 'vitest';

import { createSocketAuthCallback, joinCurrentSocketSession } from './socket-session';

describe('socket session helpers', () => {
	it('reads the latest token for every connection attempt', () => {
		let token = 'old-token';
		const auth = createSocketAuthCallback(() => token);
		const callback = vi.fn();

		auth(callback);
		token = 'new-token';
		auth(callback);

		expect(callback.mock.calls).toEqual([[{ token: 'old-token' }], [{ token: 'new-token' }]]);
	});

	it('rejoins only a connected authenticated socket', () => {
		const socket = { connected: true, emit: vi.fn() };
		expect(joinCurrentSocketSession(socket, () => 'latest-token')).toBe(true);
		expect(socket.emit).toHaveBeenCalledWith('user-join', {
			auth: { token: 'latest-token' }
		});

		expect(joinCurrentSocketSession(socket, () => '')).toBe(false);
		expect(socket.emit).toHaveBeenCalledTimes(1);
	});
});
