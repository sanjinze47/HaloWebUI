type SocketLike = {
	connected?: boolean;
	emit: (event: string, payload: unknown) => void;
};

export const createSocketAuthCallback =
	(getToken: () => string | null | undefined) => (callback: (auth: { token: string }) => void) => {
		callback({ token: getToken() ?? '' });
	};

export const joinCurrentSocketSession = (
	socket: SocketLike | null | undefined,
	getToken: () => string | null | undefined
) => {
	const token = getToken();
	if (!socket?.connected || !token) {
		return false;
	}

	socket.emit('user-join', { auth: { token } });
	return true;
};
