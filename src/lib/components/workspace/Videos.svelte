<script lang="ts">
	import { getContext, onDestroy, onMount, tick } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { Download, RefreshCw, Trash2, Upload, Video, X } from 'lucide-svelte';

	import {
		createVideoGeneration,
		deleteVideoJob,
		getVideoJobs,
		getVideoModels
	} from '$lib/apis/videos';
	import type {
		VideoGenerationJob,
		VideoGenerationModel,
		VideoGenerationSupport
	} from '$lib/apis/videos';
	import { uploadFile } from '$lib/apis/files';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { WEBUI_NAME, config, user } from '$lib/stores';
	import { canAccessVideoGeneration } from '$lib/utils/video-access';

	const i18n = getContext<any>('i18n');

	type VideoPrefs = {
		model?: string;
		duration?: number;
		aspect_ratio?: string;
		resolution?: string;
	};

	const PREFS_VERSION = 'v1';
	const ACTIVE_STATUSES = new Set(['submitting', 'pending', 'downloading']);
	const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

	let accessChecked = false;
	let allowed = false;
	let models: VideoGenerationModel[] = [];
	let jobs: VideoGenerationJob[] = [];
	let selectedModel = '';
	let selectedModelMeta: VideoGenerationModel | null = null;
	let selectedSupport: VideoGenerationSupport = {};
	let prompt = '';
	let duration = 8;
	let aspectRatio = '16:9';
	let resolution = '720p';
	let referenceFileId = '';
	let referenceFileName = '';
	let referencePreviewUrl = '';
	let referenceUploading = false;
	let loadingModels = false;
	let loadingJobs = false;
	let refreshing = false;
	let submitting = false;
	let fileInput: HTMLInputElement;
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let polling = false;
	let preferencesReady = false;
	let userId = 'anonymous';

	$: durationMin = selectedSupport.duration?.min ?? 1;
	$: durationMax = selectedSupport.duration?.max ?? 15;
	$: durationDefault = selectedSupport.duration?.default ?? 8;
	$: aspectRatioOptions = selectedSupport.aspect_ratios ?? [];
	$: resolutionOptions = selectedSupport.resolutions ?? [];
	$: supportsTextToVideo = selectedSupport.text_to_video === true;
	$: supportsImageToVideo = selectedSupport.image_to_video === true;
	$: canSubmit = Boolean(
		allowed &&
		selectedModel &&
		!submitting &&
		!referenceUploading &&
		(prompt.trim() || referenceFileId) &&
		(!referenceFileId || supportsImageToVideo) &&
		(prompt.trim() || !referenceFileId || supportsImageToVideo)
	);

	$: if (selectedModel) {
		selectedModelMeta = models.find((model) => getModelSelectionValue(model) === selectedModel) ?? null;
		selectedSupport = selectedModelMeta?.video_generation_support ?? {};
	}

	$: if (preferencesReady && typeof localStorage !== 'undefined') {
		const prefs: VideoPrefs = {
			model: selectedModel || undefined,
			duration,
			aspect_ratio: aspectRatio,
			resolution
		};
		localStorage.setItem(getPrefsKey(), JSON.stringify(prefs));
	}

	const getPrefsKey = () => `workspace:video-studio:prefs:${PREFS_VERSION}:${userId}`;

	const getModelSelectionValue = (model: VideoGenerationModel) =>
		`${model.selection_id ?? model.selection_key ?? model.id}`;

	const getModelLabel = (model: VideoGenerationModel) => model.name || model.id;

	const getSupportForModel = (model: VideoGenerationModel | null) =>
		model?.video_generation_support ?? {};

	const clampDuration = (value: number, support: VideoGenerationSupport) => {
		const min = support.duration?.min ?? 1;
		const max = support.duration?.max ?? 15;
		return Math.min(max, Math.max(min, Number.isFinite(value) ? value : support.duration?.default ?? 8));
	};

	const applyModelDefaults = (model: VideoGenerationModel | null, prefs: VideoPrefs = {}) => {
		const support = getSupportForModel(model);
		const ratios = support.aspect_ratios ?? [];
		const resolutions = support.resolutions ?? [];
		const modelDuration = clampDuration(
			prefs.duration ?? support.duration?.default ?? durationDefault,
			support
		);

		duration = modelDuration;
		aspectRatio = ratios.includes(prefs.aspect_ratio ?? '')
			? (prefs.aspect_ratio as string)
			: ratios[0] ?? '16:9';
		resolution = resolutions.includes(prefs.resolution ?? '')
			? (prefs.resolution as string)
			: resolutions[0] ?? '720p';
	};

	const normalizeModels = (items: VideoGenerationModel[]) =>
		items.filter(
			(model) =>
				model.video_generation_supported === true &&
				Boolean(model.video_generation_support)
		);

	const loadPreferences = (): VideoPrefs => {
		if (typeof localStorage === 'undefined') return {};
		try {
			const raw = localStorage.getItem(getPrefsKey());
			return raw ? (JSON.parse(raw) as VideoPrefs) : {};
		} catch {
			return {};
		}
	};

	const loadModels = async (prefs: VideoPrefs = {}) => {
		loadingModels = true;
		try {
			models = normalizeModels(await getVideoModels(localStorage.token));
			const preferred = models.find((model) => getModelSelectionValue(model) === prefs.model);
			const model = preferred ?? models[0] ?? null;
			selectedModel = model ? getModelSelectionValue(model) : '';
			selectedModelMeta = model;
			selectedSupport = getSupportForModel(model);
			applyModelDefaults(model, preferred ? prefs : {});
		} catch (error) {
			models = [];
			toast.error(formatError(error, 'Unable to load video models'));
		} finally {
			loadingModels = false;
		}
	};

	const loadJobs = async () => {
		loadingJobs = true;
		try {
			jobs = await getVideoJobs(localStorage.token, { limit: 50 });
		} catch (error) {
			toast.error(formatError(error, 'Unable to load video history'));
		} finally {
			loadingJobs = false;
		}
	};

	const refreshJobs = async () => {
		if (polling || document.visibilityState !== 'visible') return;
		polling = true;
		try {
			jobs = await getVideoJobs(localStorage.token, { limit: 50 });
		} catch (error) {
			console.warn('Video job refresh failed', error);
		} finally {
			polling = false;
		}
	};

	const startPolling = () => {
		if (pollTimer || !jobs.some((job) => ACTIVE_STATUSES.has(job.status))) return;
		pollTimer = setInterval(refreshJobs, 4000);
	};

	const stopPolling = () => {
		if (pollTimer) clearInterval(pollTimer);
		pollTimer = null;
	};

	$: if (jobs.length > 0) {
		if (
			jobs.some((job) => ACTIVE_STATUSES.has(job.status)) &&
			typeof document !== 'undefined' &&
			document.visibilityState === 'visible'
		) {
			startPolling();
		} else if (!jobs.some((job) => ACTIVE_STATUSES.has(job.status))) {
			stopPolling();
		}
	}

	const handleVisibilityChange = () => {
		if (document.visibilityState === 'visible') {
			void refreshJobs();
			startPolling();
		} else {
			stopPolling();
		}
	};

	const selectModel = (value: string) => {
		selectedModel = value;
		const model = models.find((item) => getModelSelectionValue(item) === value) ?? null;
		selectedModelMeta = model;
		selectedSupport = getSupportForModel(model);
		applyModelDefaults(model);
	};

	const handleDurationInput = (value: string) => {
		duration = clampDuration(Number(value), selectedSupport);
	};

	const handleDurationInputEvent = (event: Event) => {
		const target = event.currentTarget;
		if (target instanceof HTMLInputElement) handleDurationInput(target.value);
	};

	const handleReferenceFileChange = async (event: Event) => {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;

		if (!IMAGE_TYPES.has(file.type)) {
			toast.error($i18n.t('Only JPEG, PNG, and WebP images are supported.'));
			return;
		}
		if (file.size > 20 * 1024 * 1024) {
			toast.error($i18n.t('Reference images must be 20 MiB or smaller.'));
			return;
		}

		removeReferencePreview();
		referencePreviewUrl = URL.createObjectURL(file);
		referenceFileName = file.name;
		referenceUploading = true;
		try {
			const uploaded = (await uploadFile(localStorage.token, file, { process: false })) as {
				id?: string;
				file_id?: string;
			};
			referenceFileId = uploaded?.id ?? uploaded?.file_id ?? '';
			if (!referenceFileId) throw new Error($i18n.t('The uploaded image did not return a file ID.'));
		} catch (error) {
			referenceFileId = '';
			referenceFileName = '';
			removeReferencePreview();
			toast.error(formatError(error, 'Unable to upload reference image'));
		} finally {
			referenceUploading = false;
		}
	};

	const removeReferencePreview = () => {
		if (referencePreviewUrl) URL.revokeObjectURL(referencePreviewUrl);
		referencePreviewUrl = '';
	};

	const removeReference = () => {
		referenceFileId = '';
		referenceFileName = '';
		removeReferencePreview();
	};

	const submitHandler = async () => {
		const trimmedPrompt = prompt.trim();
		if (!selectedModel) {
			toast.error($i18n.t('Select a video model first.'));
			return;
		}
		if (!trimmedPrompt && !referenceFileId) {
			toast.error($i18n.t('Enter a prompt or add a reference image.'));
			return;
		}
		if (referenceFileId && !supportsImageToVideo) {
			toast.error($i18n.t('The selected model does not support image-to-video generation.'));
			return;
		}
		if (trimmedPrompt && !referenceFileId && !supportsTextToVideo) {
			toast.error($i18n.t('The selected model does not support text-to-video generation.'));
			return;
		}

		submitting = true;
		try {
			const job = await createVideoGeneration(localStorage.token, {
				model: selectedModel,
				...(trimmedPrompt ? { prompt: trimmedPrompt } : {}),
				...(referenceFileId ? { reference_file_id: referenceFileId } : {}),
				duration: clampDuration(duration, selectedSupport),
				aspect_ratio: aspectRatio,
				resolution
			});
			jobs = [job, ...jobs.filter((item) => item.id !== job.id)].slice(0, 50);
			prompt = '';
			await tick();
			startPolling();
			toast.success($i18n.t('Video generation started.'));
		} catch (error) {
			toast.error(formatError(error, 'Unable to start video generation'));
		} finally {
			submitting = false;
		}
	};

	const isTerminalJob = (job: VideoGenerationJob) =>
		!ACTIVE_STATUSES.has(job.status);

	const getJobError = (job: VideoGenerationJob) => {
		if (typeof job.error === 'string') return job.error;
		return job.error?.message || job.error_message || $i18n.t('Video generation failed.');
	};

	const getVideoUrl = (job: VideoGenerationJob) => {
		if (job.result_file_id) {
			return `${WEBUI_API_BASE_URL}/files/${encodeURIComponent(job.result_file_id)}/content`;
		}
		const candidate = job.result_file_url || job.result_url || job.result_file?.url;
		return typeof candidate === 'string' && candidate.startsWith('/') ? candidate : '';
	};

	const hasMissingResult = (job: VideoGenerationJob) =>
		job.status === 'completed' && (job.file_exists === false || !getVideoUrl(job));

	const deleteJob = async (job: VideoGenerationJob) => {
		if (!isTerminalJob(job)) return;
		try {
			await deleteVideoJob(localStorage.token, job.id);
			jobs = jobs.filter((item) => item.id !== job.id);
		} catch (error) {
			toast.error(formatError(error, 'Unable to delete video history'));
		}
	};

	const formatError = (error: unknown, fallback: string) => {
		if (typeof error === 'string' && error.trim()) return error;
		if (error instanceof Error && error.message) return error.message;
		if (error && typeof error === 'object') {
			const value = error as { detail?: unknown; message?: unknown };
			if (typeof value.detail === 'string') return value.detail;
			if (typeof value.message === 'string') return value.message;
		}
		return $i18n.t(fallback);
	};

	const formatDate = (value: string | number | undefined) => {
		if (!value) return '';
		const numeric = typeof value === 'number' ? value : Number(value);
		const date = new Date(
			Number.isFinite(numeric) && numeric > 0 && numeric < 100000000000
				? numeric * 1000
				: value
		);
		return Number.isNaN(date.getTime()) ? `${value}` : date.toLocaleString();
	};

	onMount(async () => {
		userId = $user?.id ?? 'anonymous';
		allowed = canAccessVideoGeneration($config, $user);
		accessChecked = true;
		if (!allowed) {
			await goto('/');
			return;
		}

		document.addEventListener('visibilitychange', handleVisibilityChange);
		const prefs = loadPreferences();
		await Promise.all([loadModels(prefs), loadJobs()]);
		preferencesReady = true;
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
		if (typeof document !== 'undefined') {
			document.removeEventListener('visibilitychange', handleVisibilityChange);
		}
		removeReferencePreview();
	});
</script>

<svelte:head>
	<title>{$i18n.t('Videos')} | {$WEBUI_NAME}</title>
</svelte:head>

{#if accessChecked && allowed}
	<div class="space-y-6 pb-4">
		<section class="glass-section p-5 space-y-5">
			<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<div class="flex items-start gap-3">
					<div class="glass-icon-badge bg-indigo-50 dark:bg-indigo-950/30">
						<Video class="size-[18px] text-indigo-500 dark:text-indigo-400" />
					</div>
					<div>
						<h1 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Video Generation')}</h1>
						<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
							{$i18n.t('Create a short video from a prompt or one reference image.')}
						</p>
					</div>
				</div>
				<button
					type="button"
					class="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800"
					on:click={() => void Promise.all([loadModels(loadPreferences()), loadJobs()])}
					disabled={loadingModels || loadingJobs || refreshing}
				>
					<RefreshCw class={`size-4 ${loadingModels || loadingJobs ? 'animate-spin' : ''}`} />
					<span>{$i18n.t('Refresh')}</span>
				</button>
			</div>

			{#if loadingModels}
				<div class="flex items-center gap-2 text-sm text-gray-500"><Spinner className="size-4" /> {$i18n.t('Loading video models...')}</div>
			{:else if models.length === 0}
				<div class="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
					{$i18n.t('No video-capable models are available. Ask an administrator to configure a grok2api OpenAI connection.')}
				</div>
			{:else}
				<div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.8fr)]">
					<form class="space-y-4" on:submit|preventDefault={submitHandler}>
						<div class="glass-item p-4 space-y-4">
							<div class="space-y-1.5">
								<label class="text-xs font-medium text-gray-500 dark:text-gray-400" for="video-model">
									{$i18n.t('Model')}
								</label>
								<HaloSelect
									triggerId="video-model"
									value={selectedModel}
									options={models.map((model) => ({
										value: getModelSelectionValue(model),
										label: getModelLabel(model)
									}))}
									className="w-full"
									on:change={(event) => selectModel(event.detail.value)}
								/>
							</div>

							<div class="space-y-1.5">
								<label class="text-xs font-medium text-gray-500 dark:text-gray-400" for="video-prompt">
									{$i18n.t('Prompt')}
								</label>
								<textarea
									id="video-prompt"
									bind:value={prompt}
									rows="5"
									class="w-full resize-y rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm text-gray-800 outline-none transition focus:border-indigo-400 dark:border-gray-700 dark:bg-gray-950/60 dark:text-gray-100"
									placeholder={$i18n.t('Describe the motion, subject, camera, and atmosphere...')}
								/>
							</div>

							<div class="space-y-2">
								<div class="flex items-center justify-between gap-3">
									<div class="text-xs font-medium text-gray-500 dark:text-gray-400">{$i18n.t('Reference Image')}</div>
									<span class="text-[11px] text-gray-400">{$i18n.t('Optional, one image')}</span>
								</div>
								{#if referencePreviewUrl}
									<div class="flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-900/50">
										<img src={referencePreviewUrl} alt={referenceFileName} class="size-16 rounded-lg object-cover" />
										<div class="min-w-0 flex-1">
											<div class="truncate text-sm text-gray-700 dark:text-gray-200">{referenceFileName}</div>
											<div class="text-xs text-gray-400">{referenceUploading ? $i18n.t('Uploading...') : $i18n.t('Ready')}</div>
										</div>
										<button type="button" class="rounded-lg p-2 text-gray-400 transition hover:bg-white hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200" on:click={removeReference} aria-label={$i18n.t('Remove reference image')}>
											<X class="size-4" />
										</button>
									</div>
								{:else}
									<button type="button" class="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-gray-300 px-4 py-4 text-sm font-medium text-gray-600 transition hover:border-indigo-400 hover:bg-indigo-50/40 dark:border-gray-700 dark:text-gray-300 dark:hover:border-indigo-500 dark:hover:bg-indigo-950/20" on:click={() => fileInput?.click()}>
										<Upload class="size-4" />
										<span>{$i18n.t('Upload reference image')}</span>
									</button>
								{/if}
								<input bind:this={fileInput} class="hidden" type="file" accept="image/jpeg,image/png,image/webp" on:change={handleReferenceFileChange} />
							</div>
						</div>

						<div class="glass-item p-4 space-y-4">
							<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Generation Settings')}</div>
							<div class="grid gap-4 sm:grid-cols-3">
								<div class="space-y-1.5">
									<div class="flex items-center justify-between text-xs font-medium text-gray-500 dark:text-gray-400">
										<span>{$i18n.t('Duration')}</span><span>{duration}s</span>
									</div>
									<input type="range" min={durationMin} max={durationMax} step="1" value={duration} on:input={handleDurationInputEvent} class="h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-200 dark:bg-gray-800" />
									<div class="text-[11px] text-gray-400">{durationMin}-{durationMax}s</div>
								</div>
								<div class="space-y-1.5">
									<label class="text-xs font-medium text-gray-500 dark:text-gray-400" for="video-aspect-ratio">{$i18n.t('Aspect Ratio')}</label>
									<HaloSelect
										triggerId="video-aspect-ratio"
										value={aspectRatio}
										options={aspectRatioOptions.map((value) => ({ value, label: value }))}
										className="w-full"
										on:change={(event) => (aspectRatio = event.detail.value)}
									/>
								</div>
								<div class="space-y-1.5">
									<label class="text-xs font-medium text-gray-500 dark:text-gray-400" for="video-resolution">{$i18n.t('Resolution')}</label>
									<HaloSelect
										triggerId="video-resolution"
										value={resolution}
										options={resolutionOptions.map((value) => ({ value, label: value }))}
										className="w-full"
										on:change={(event) => (resolution = event.detail.value)}
									/>
								</div>
							</div>
							<div class="flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
								<span class="rounded-md bg-gray-100 px-2 py-1 dark:bg-gray-800">{supportsTextToVideo ? $i18n.t('Text to video') : $i18n.t('Text to video unavailable')}</span>
								<span class="rounded-md bg-gray-100 px-2 py-1 dark:bg-gray-800">{supportsImageToVideo ? $i18n.t('Image to video') : $i18n.t('Image to video unavailable')}</span>
							</div>
							<button type="submit" class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50" disabled={!canSubmit}>
								{#if submitting}<Spinner className="size-4" />{:else}<Video class="size-4" />{/if}
								<span>{submitting ? $i18n.t('Starting...') : $i18n.t('Generate Video')}</span>
							</button>
						</div>
					</form>

					<section class="glass-section min-w-0 p-4 space-y-3">
						<div class="flex items-center justify-between gap-3">
							<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{$i18n.t('Recent Video Jobs')}</div>
							{#if loadingJobs}<Spinner className="size-4" />{/if}
						</div>
						{#if jobs.length === 0}
							<div class="rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">{$i18n.t('Your generated videos will appear here.')}</div>
						{:else}
							<div class="space-y-3">
								{#each jobs as job (job.id)}
									{@const videoUrl = getVideoUrl(job)}
									<div class="rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900/50">
										<div class="flex items-start justify-between gap-3">
											<div class="min-w-0 flex-1">
												<div class="truncate text-sm font-medium text-gray-800 dark:text-gray-100">{job.prompt || $i18n.t('Image-to-video generation')}</div>
												<div class="mt-1 text-xs text-gray-400">{job.model || selectedModel} {formatDate(job.created_at)}</div>
											</div>
											<span class="shrink-0 rounded-md px-2 py-1 text-[11px] font-medium {job.status === 'completed' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' : job.status === 'failed' || job.status === 'timed_out' ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300' : 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300'}">{job.status}</span>
										</div>
										{#if ACTIVE_STATUSES.has(job.status)}
											<div class="mt-3 space-y-1">
												<div class="flex justify-between text-xs text-gray-500"><span>{$i18n.t('Progress')}</span><span>{job.progress ?? 0}%</span></div>
												<div class="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800"><div class="h-full rounded-full bg-indigo-500 transition-all" style={`width: ${Math.min(100, Math.max(0, job.progress ?? 0))}%`}></div></div>
											</div>
										{:else if job.status === 'completed' && videoUrl}
											<video class="mt-3 aspect-video w-full rounded-lg bg-black object-contain" controls preload="metadata" src={videoUrl}>
												<track kind="captions" srclang="en" label={$i18n.t('Captions')} />
											</video>
										{:else if job.status === 'completed' && hasMissingResult(job)}
											<div class="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-300">{$i18n.t('The generated video file is no longer available.')}</div>
										{:else if job.status === 'failed' || job.status === 'timed_out'}
											<div class="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-700 dark:bg-rose-950/30 dark:text-rose-300">{getJobError(job)}</div>
										{/if}
										{#if isTerminalJob(job)}
											<div class="mt-3 flex items-center justify-end gap-2">
												{#if videoUrl}
													<a class="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-600 transition hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800" href={videoUrl} download={job.result_file_name || 'generated-video.mp4'}><Download class="size-3.5" />{$i18n.t('Download')}</a>
												{/if}
												<button type="button" class="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 dark:border-rose-900/60 dark:text-rose-300 dark:hover:bg-rose-950/30" on:click={() => void deleteJob(job)}><Trash2 class="size-3.5" />{$i18n.t('Delete')}</button>
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</section>
				</div>
			{/if}
		</section>
	</div>
{/if}
