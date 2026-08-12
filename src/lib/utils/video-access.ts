export const isVideoGenerationGloballyEnabled = (backendConfig: any): boolean =>
	backendConfig?.features?.enable_video_generation === true ||
	backendConfig?.enable_video_generation === true;

export const canAccessVideoGeneration = (backendConfig: any, sessionUser: any): boolean =>
	isVideoGenerationGloballyEnabled(backendConfig) &&
	(sessionUser?.role === 'admin' || sessionUser?.permissions?.features?.video_generation === true);
