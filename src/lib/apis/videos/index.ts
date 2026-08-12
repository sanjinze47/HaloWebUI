import { WEBUI_API_BASE_URL } from '$lib/constants';
import { parseJsonResponse } from '../response';

export type VideoGenerationSupport = {
	mode?: string;
	async?: boolean;
	text_to_video?: boolean;
	image_to_video?: boolean;
	max_reference_images?: number;
	duration?: {
		min?: number;
		max?: number;
		default?: number;
	};
	aspect_ratios?: string[];
	resolutions?: string[];
};

export type VideoGenerationModel = {
	id: string;
	name?: string;
	selection_id?: string;
	selection_key?: string;
	model_ref?: Record<string, unknown> | null;
	video_generation_supported?: boolean;
	video_generation_support?: VideoGenerationSupport | null;
	[key: string]: unknown;
};

export type VideoGenerationConfig = {
	enabled?: boolean;
	shared_key_enabled?: boolean;
	enable_video_generation?: boolean;
	enable_video_generation_shared_key?: boolean;
};

export type VideoGenerationRequest = {
	model: string;
	prompt?: string;
	reference_file_id?: string;
	duration: number;
	aspect_ratio: string;
	resolution: string;
};

export type VideoGenerationJobStatus =
	| 'submitting'
	| 'pending'
	| 'downloading'
	| 'completed'
	| 'failed'
	| 'timed_out'
	| string;

export type VideoGenerationJob = {
	id: string;
	model?: string;
	model_ref?: Record<string, unknown> | null;
	prompt?: string;
	reference_file_id?: string | null;
	duration?: number;
	aspect_ratio?: string;
	resolution?: string;
	status: VideoGenerationJobStatus;
	progress?: number | null;
	error?: { code?: string; message?: string } | string | null;
	error_code?: string | null;
	error_message?: string | null;
	result_file_id?: string | null;
	result_file_name?: string | null;
	result_file_url?: string | null;
	result_url?: string | null;
	result_file?: { id?: string; name?: string; url?: string } | null;
	file_exists?: boolean;
	created_at?: string | number;
	updated_at?: string | number;
	completed_at?: string | number | null;
	[key: string]: unknown;
};

export type VideoGenerationJobsResponse = {
	items?: VideoGenerationJob[];
	jobs?: VideoGenerationJob[];
	total?: number;
	[key: string]: unknown;
};

const headers = (token: string) => ({
	Accept: 'application/json',
	'Content-Type': 'application/json',
	...(token && { authorization: `Bearer ${token}` })
});

const requestJson = async <T>(
	token: string,
	path: string,
	options: RequestInit = {}
): Promise<T> => {
	const response = await fetch(`${WEBUI_API_BASE_URL}/videos${path}`, {
		...options,
		headers: {
			...headers(token),
			...(options.headers ?? {})
		}
	});

	return parseJsonResponse<T>(response);
};

const unwrapConfig = (payload: unknown): VideoGenerationConfig => {
	if (payload && typeof payload === 'object' && 'config' in payload) {
		return ((payload as { config?: VideoGenerationConfig }).config ?? {}) as VideoGenerationConfig;
	}
	return (payload ?? {}) as VideoGenerationConfig;
};

const unwrapModels = (
	payload: VideoGenerationModel[] | { models?: VideoGenerationModel[]; items?: VideoGenerationModel[] }
) => (Array.isArray(payload) ? payload : payload?.models ?? payload?.items ?? []);

const unwrapJobs = (
	payload: VideoGenerationJob[] | VideoGenerationJobsResponse
): VideoGenerationJob[] => (Array.isArray(payload) ? payload : payload?.jobs ?? payload?.items ?? []);

const unwrapJob = (payload: unknown): VideoGenerationJob => {
	if (payload && typeof payload === 'object' && 'job' in payload) {
		return ((payload as { job?: VideoGenerationJob }).job ?? payload) as VideoGenerationJob;
	}
	return payload as VideoGenerationJob;
};

export const getVideoConfig = async (token: string = ''): Promise<VideoGenerationConfig> =>
	unwrapConfig(await requestJson(token, '/config'));

export const updateVideoConfig = async (
	token: string = '',
	config: Pick<VideoGenerationConfig, 'enabled' | 'shared_key_enabled'>
): Promise<VideoGenerationConfig> =>
	unwrapConfig(
		await requestJson(token, '/config/update', {
			method: 'POST',
			body: JSON.stringify(config)
		})
	);

export const getVideoModels = async (token: string = ''): Promise<VideoGenerationModel[]> =>
	unwrapModels(await requestJson(token, '/models'));

export const createVideoGeneration = async (
	token: string = '',
	request: VideoGenerationRequest
): Promise<VideoGenerationJob> =>
	unwrapJob(
		await requestJson(token, '/generations', {
			method: 'POST',
			body: JSON.stringify(request)
		})
	);

export const getVideoJobs = async (
	token: string = '',
	params: { skip?: number; limit?: number } = {}
): Promise<VideoGenerationJob[]> => {
	const query = new URLSearchParams();
	if (Number.isInteger(params.skip)) query.set('skip', `${params.skip}`);
	if (Number.isInteger(params.limit)) query.set('limit', `${params.limit}`);
	const suffix = query.toString() ? `?${query}` : '';
	return unwrapJobs(await requestJson(token, `/jobs${suffix}`));
};

export const getVideoJob = async (
	token: string = '',
	id: string
): Promise<VideoGenerationJob> => unwrapJob(await requestJson(token, `/jobs/${encodeURIComponent(id)}`));

export const deleteVideoJob = async (token: string = '', id: string) =>
	requestJson(token, `/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const getConfig = getVideoConfig;
export const updateConfig = updateVideoConfig;
export const getModels = getVideoModels;
export const createGeneration = createVideoGeneration;
export const getJobs = getVideoJobs;
export const getJob = getVideoJob;
export const deleteJob = deleteVideoJob;
