<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext, onMount, tick } from 'svelte';
	import { config as backendConfig, user } from '$lib/stores';
	import { getBackendConfig } from '$lib/apis';
	import { getConfig, updateConfig, getImageGenerationConfig, updateImageGenerationConfig } from '$lib/apis/images';
	import { getVideoConfig, updateVideoConfig } from '$lib/apis/videos';
	import Switch from '$lib/components/common/Switch.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import InlineDirtyActions from './InlineDirtyActions.svelte';
	import { cloneSettingsSnapshot, isSettingsSnapshotEqual } from '$lib/utils/settings-dirty';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	let loading = false;
	let config = null;
	let imageGenerationConfig = { IMAGE_MODEL_FILTER_REGEX: '' };
	let videoGenerationConfig = { enabled: false, shared_key_enabled: false };
	let videoConfigLoaded = false;
	let initialSnapshot = null;

	const getErrorText = (error) => {
		if (typeof error === 'string') return error;
		if (error instanceof Error) return error.message;
		if (Array.isArray(error)) return error.map(getErrorText).filter(Boolean).join(', ');
		if (error && typeof error === 'object') {
			const value = error as Record<string, unknown>;
			const message =
				typeof value.msg === 'string'
					? value.msg
					: typeof value.message === 'string'
						? value.message
						: '';
			const loc = Array.isArray(value.loc)
				? value.loc
						.filter((part) => part !== 'body')
						.map((part) => `${part}`)
						.join('.')
				: '';
			if (message) return loc ? `${loc}: ${message}` : message;
			if ('detail' in value) return getErrorText(value.detail);

			try {
				return JSON.stringify(value);
			} catch {
				return '';
			}
		}
		return `${error ?? ''}`;
	};

	const formatImageSettingsError = (error) => {
		const message = getErrorText(error).trim();
		return message ? $i18n.t(message) : $i18n.t('Connection failed');
	};

	const normalizeImageSettingsSnapshot = (
		sourceConfig = config,
		sourceImageConfig = imageGenerationConfig,
		sourceVideoConfig = videoGenerationConfig
	) => ({
		enabled: sourceConfig?.enabled === true,
		shared_key_enabled: sourceConfig?.shared_key_enabled === true,
		IMAGE_MODEL_FILTER_REGEX: `${sourceImageConfig?.IMAGE_MODEL_FILTER_REGEX ?? ''}`,
		video_enabled: sourceVideoConfig?.enabled === true,
		video_shared_key_enabled: sourceVideoConfig?.shared_key_enabled === true
	});

	$: snapshot = normalizeImageSettingsSnapshot(config, imageGenerationConfig, videoGenerationConfig);
	$: isDirty = !!(initialSnapshot && config && !isSettingsSnapshotEqual(snapshot, initialSnapshot));

	const syncBaseline = (
		sourceConfig = config,
		sourceImageConfig = imageGenerationConfig,
		sourceVideoConfig = videoGenerationConfig
	) => {
		initialSnapshot = cloneSettingsSnapshot(
			normalizeImageSettingsSnapshot(sourceConfig, sourceImageConfig, sourceVideoConfig)
		);
	};

	const resetChanges = () => {
		if (!initialSnapshot) return;
		config = {
			...config,
			enabled: initialSnapshot.enabled,
			shared_key_enabled: initialSnapshot.shared_key_enabled
		};
		imageGenerationConfig = {
			...imageGenerationConfig,
			IMAGE_MODEL_FILTER_REGEX: initialSnapshot.IMAGE_MODEL_FILTER_REGEX
		};
		videoGenerationConfig = {
			...videoGenerationConfig,
			enabled: initialSnapshot.video_enabled,
			shared_key_enabled: initialSnapshot.video_shared_key_enabled
		};
	};

	const serializeConfigForSave = (draftConfig) => ({
		enabled: draftConfig?.enabled === true,
		shared_key_enabled: draftConfig?.shared_key_enabled === true
	});

	const serializeImageGenerationConfigForSave = (draftImageConfig) => ({
		IMAGE_MODEL_FILTER_REGEX: `${draftImageConfig?.IMAGE_MODEL_FILTER_REGEX ?? ''}`
	});

	const serializeVideoGenerationConfigForSave = (draftVideoConfig) => ({
		enabled: draftVideoConfig?.enabled === true,
		shared_key_enabled: draftVideoConfig?.shared_key_enabled === true
	});

	const loadImageSettings = async () => {
		const [loadedConfig, loadedImageConfig, loadedVideoConfig] = await Promise.all([
			getConfig(localStorage.token).catch((error) => {
				toast.error(formatImageSettingsError(error));
				return null;
			}),
			getImageGenerationConfig(localStorage.token).catch((error) => {
				toast.error(formatImageSettingsError(error));
				return null;
			}),
			getVideoConfig(localStorage.token).catch((error) => {
				videoConfigLoaded = false;
				return null;
			})
		]);

		if (loadedConfig) config = normalizeImageSettingsSnapshot(loadedConfig, imageGenerationConfig);
		if (loadedImageConfig) {
			imageGenerationConfig = {
				...imageGenerationConfig,
				IMAGE_MODEL_FILTER_REGEX: `${loadedImageConfig?.IMAGE_MODEL_FILTER_REGEX ?? ''}`
			};
		}
		if (loadedVideoConfig) {
			videoConfigLoaded = true;
			videoGenerationConfig = {
				...videoGenerationConfig,
				enabled: loadedVideoConfig?.enabled === true,
				shared_key_enabled: loadedVideoConfig?.shared_key_enabled === true
			};
		}
	};

	const saveHandler = async () => {
		loading = true;

		const updatedConfig = await updateConfig(localStorage.token, serializeConfigForSave(config)).catch((error) => {
			toast.error(formatImageSettingsError(error));
			return null;
		});

		const updatedImageGenerationConfig = await updateImageGenerationConfig(
			localStorage.token,
			serializeImageGenerationConfigForSave(imageGenerationConfig)
		).catch((error) => {
			toast.error(formatImageSettingsError(error));
			return null;
		});
		const updatedVideoConfig = videoConfigLoaded
			? await updateVideoConfig(
					localStorage.token,
					serializeVideoGenerationConfigForSave(videoGenerationConfig)
				  ).catch((error) => {
					toast.error(formatImageSettingsError(error));
					return null;
				  })
			: videoGenerationConfig;

		if (!updatedConfig || !updatedImageGenerationConfig || (videoConfigLoaded && !updatedVideoConfig)) {
			loading = false;
			return;
		}

		config = normalizeImageSettingsSnapshot(updatedConfig, imageGenerationConfig);
		imageGenerationConfig = {
			...imageGenerationConfig,
			IMAGE_MODEL_FILTER_REGEX: `${updatedImageGenerationConfig?.IMAGE_MODEL_FILTER_REGEX ?? ''}`
		};
		if (updatedVideoConfig) {
			videoGenerationConfig = {
				...videoGenerationConfig,
				enabled: updatedVideoConfig?.enabled === true,
				shared_key_enabled: updatedVideoConfig?.shared_key_enabled === true
			};
		}
		backendConfig.set(await getBackendConfig());
		await tick();
		syncBaseline(config, imageGenerationConfig, videoGenerationConfig);
		dispatch('save');
		loading = false;
	};

	onMount(async () => {
		if ($user?.role !== 'admin') return;

		await loadImageSettings();
		await tick();
		syncBaseline();
	});
</script>

<form class="flex h-full min-h-0 flex-col text-sm" on:submit|preventDefault={saveHandler}>
	<div class="h-full space-y-6 overflow-y-auto scrollbar-hidden">
		{#if config}
			<div class="max-w-6xl mx-auto space-y-6">
				<section class="glass-section p-5 space-y-5 {isDirty ? 'glass-section-dirty' : ''}">
					<div class="flex items-center justify-between gap-3">
						<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
							{$i18n.t('Image Settings')}
						</div>
						<InlineDirtyActions dirty={isDirty} saving={loading} on:reset={resetChanges} />
					</div>

					<div class="space-y-3">
						<div class="flex items-center justify-between glass-item px-4 py-3">
							<div>
								<div class="text-sm font-medium">{$i18n.t('Image Generation')}</div>
								<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t('Users can generate images by selecting an image model in chat or in the image workspace.')}
								</div>
							</div>
							<Switch bind:state={config.enabled} />
						</div>

						<div class="flex items-center justify-between glass-item px-4 py-3">
							<div>
								<div class="text-sm font-medium">{$i18n.t('Allow users to use the workspace shared key')}</div>
								<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t('When enabled, users without personal connections can fall back to the workspace shared key.')}
								</div>
							</div>
							<Switch bind:state={config.shared_key_enabled} />
						</div>
					</div>
				</section>

				<section class="glass-section p-5 space-y-5 {isDirty ? 'glass-section-dirty' : ''}">
					<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
						{$i18n.t('Video Generation')}
					</div>
					<div class="space-y-3">
						<div class="flex items-center justify-between glass-item px-4 py-3">
							<div>
								<div class="text-sm font-medium">{$i18n.t('Video Generation')}</div>
								<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t('Allow users to create videos in the video workspace.')}
								</div>
							</div>
							<Switch bind:state={videoGenerationConfig.enabled} disabled={!videoConfigLoaded} />
						</div>

						<div class="flex items-center justify-between glass-item px-4 py-3">
							<div>
								<div class="text-sm font-medium">{$i18n.t('Allow users to use the workspace shared key')}</div>
								<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
									{$i18n.t('Use the configured shared provider key for video generation when available.')}
								</div>
							</div>
							<Switch
								bind:state={videoGenerationConfig.shared_key_enabled}
								disabled={!videoConfigLoaded}
							/>
						</div>
					</div>
				</section>

				<section class="glass-section p-5 space-y-5 {isDirty ? 'glass-section-dirty' : ''}">
					<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
						{$i18n.t('Model Filter Regex')}
					</div>
					<div class="glass-item p-4">
						<Tooltip content={$i18n.t('Regex pattern to filter image models (leave empty to show all)')} placement="top-start">
							<input
								class="w-full py-2 px-3 text-sm dark:text-gray-300 glass-input"
								placeholder={$i18n.t('e.g. dall-e|gpt-image')}
								bind:value={imageGenerationConfig.IMAGE_MODEL_FILTER_REGEX}
							/>
						</Tooltip>
					</div>
				</section>
			</div>
		{/if}
	</div>
</form>
