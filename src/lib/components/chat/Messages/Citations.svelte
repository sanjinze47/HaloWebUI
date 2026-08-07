<script lang="ts">
	import { getContext } from 'svelte';
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';
	import CitationsModal from './CitationsModal.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import { getCitationEntries } from '$lib/utils/citations';
	import { getDisplayTitle, decodeString } from '$lib/utils/marked/citation-extension';

	const i18n: any = getContext('i18n');

	type Citation = {
		id: string;
		source?: Record<string, any>;
		document: string[];
		metadata: any[];
		distances: number[];
	};

	export let id = '';
	export let sources: Record<string, any>[] = [];

	let citations: Citation[] = [];
	let showPercentage = false;
	let showRelevance = true;

	let showCitationModal = false;
	let selectedCitation: any = null;
	let showCitations = false;

	let buttonEl: HTMLElement;
	let openAbove = false;
	let faviconFailures: Record<string, boolean> = {};

	function calculateShowRelevance(sources: any[]) {
		const distances = sources.flatMap((citation) => citation.distances ?? []);
		const inRange = distances.filter((d) => d !== undefined && d >= -1 && d <= 1).length;
		const outOfRange = distances.filter((d) => d !== undefined && (d < -1 || d > 1)).length;

		if (distances.length === 0) {
			return false;
		}

		if (
			(inRange === distances.length - 1 && outOfRange === 1) ||
			(outOfRange === distances.length - 1 && inRange === 1)
		) {
			return false;
		}

		return true;
	}

	function shouldShowPercentage(sources: any[]) {
		const distances = sources.flatMap((citation) => citation.distances ?? []);
		return distances.every((d) => d !== undefined && d >= -1 && d <= 1);
	}

	function isWebCitation(citation: any): boolean {
		return (
			citation.id?.startsWith('http://') ||
			citation.id?.startsWith('https://') ||
			citation.source?.url?.includes('http') ||
			citation.source?.name?.startsWith('http://') ||
			citation.source?.name?.startsWith('https://')
		);
	}

	function getSourceUrl(citation: any): string {
		const url = citation?.source?.url ?? citation?.id ?? '';
		return typeof url === 'string' && /^https?:\/\//i.test(url) ? url : '';
	}

	function getSourceDomain(citation: any): string {
		const url = getSourceUrl(citation);
		if (!url) return '';

		try {
			return new URL(url).hostname.replace(/^www\./i, '');
		} catch {
			return '';
		}
	}

	function getFaviconUrl(citation: any): string {
		const domain = getSourceDomain(citation);
		return domain
			? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`
			: '';
	}

	function hideFavicon(citationId: string) {
		faviconFailures = { ...faviconFailures, [citationId]: true };
	}

	$: {
		citations = sources.reduce<Citation[]>((acc, source) => {
			if (!source || typeof source !== 'object' || Object.keys(source).length === 0) {
				return acc;
			}

			getCitationEntries(source).forEach(({ document, metadata, distance }) => {
				const documentText = typeof document === 'string' ? document : `${document ?? ''}`;

				const id = metadata?.source ?? source?.source?.id ?? 'N/A';
				let _source = source?.source;

				if (metadata?.name) {
					_source = { ..._source, name: metadata.name };
				}

				if (id.startsWith('http://') || id.startsWith('https://')) {
					_source = { ..._source, name: id, url: id };
				}

				const existingSource = acc.find((item) => item.id === id);

				if (existingSource) {
					existingSource.document.push(documentText);
					existingSource.metadata.push(metadata);
					if (distance !== undefined) existingSource.distances.push(distance);
				} else {
					acc.push({
						id: id,
						source: _source,
						document: [documentText],
						metadata: metadata ? [metadata] : [],
						distances: distance !== undefined ? [distance] : []
					});
				}
			});

			return acc;
		}, []);

		showRelevance = calculateShowRelevance(citations);
		showPercentage = shouldShowPercentage(citations);
	}

	function normalizeCitationIndex(indexOrIdentifier: number | string | null | undefined): number | null {
		if (typeof indexOrIdentifier === 'number' && Number.isInteger(indexOrIdentifier)) {
			return indexOrIdentifier;
		}

		if (typeof indexOrIdentifier === 'string') {
			const match = indexOrIdentifier.match(/^(\d+)/);
			if (match) {
				return Number.parseInt(match[1], 10);
			}
		}

		return null;
	}

	export function openCitationByIndex(indexOrIdentifier: number | string | null | undefined): boolean {
		const index = normalizeCitationIndex(indexOrIdentifier);
		if (index === null || index < 1) {
			return false;
		}

		const citation = citations[index - 1];
		if (!citation) {
			return false;
		}

		selectedCitation = citation;
		showCitationModal = true;
		return true;
	}
</script>

<CitationsModal
	bind:show={showCitationModal}
	citation={selectedCitation}
	{showPercentage}
	{showRelevance}
/>

{#if citations.length > 0}
	{@const hasWebCitations = citations.some((c) => isWebCitation(c))}
	<div class="-mx-0.5 relative flex w-full flex-wrap items-center gap-2">
		<!-- Compact pill button -->
		<button
			bind:this={buttonEl}
			class="text-xs font-medium text-gray-600 dark:text-gray-300 px-3 rounded-xl
				bg-white/60 dark:bg-gray-800/60 backdrop-blur-xl
				hover:bg-white/80 dark:hover:bg-gray-700/60 transition-all duration-200
				flex items-center gap-1.5
				border border-gray-200/50 dark:border-gray-700/50"
			style="height: 36px;"
			on:click={() => {
				if (!showCitations && buttonEl) {
					const rect = buttonEl.getBoundingClientRect();
					const spaceBelow = window.innerHeight - rect.bottom;
					openAbove = spaceBelow < 260;
				}
				showCitations = !showCitations;
			}}
		>
			{#if hasWebCitations}
				<GlobeAlt className="size-4 shrink-0" strokeWidth="2" />
			{:else}
				<Document className="size-4 shrink-0" strokeWidth="2" />
			{/if}
			<span class="translate-y-px">
				{#if citations.length === 1}
					{$i18n.t('1 Source')}
				{:else}
					{$i18n.t('{{COUNT}} Sources', { COUNT: citations.length })}
				{/if}
			</span>
			<div class="shrink-0 transition-transform duration-200" class:rotate-180={showCitations}>
				<ChevronDown strokeWidth="3.5" className="size-3.5" />
			</div>
		</button>

		<!-- OpenAI-style source cards -->
		<div class="flex w-full gap-2 overflow-x-auto pb-0.5 scrollbar-none">
			{#each citations.slice(0, 8) as citation, idx}
				{@const sourceUrl = getSourceUrl(citation)}
				{@const domain = getSourceDomain(citation)}
				{@const faviconUrl = getFaviconUrl(citation)}
				<button
					class="flex min-w-[190px] max-w-[260px] flex-1 items-center gap-2 rounded-lg border border-gray-200/70 bg-white/70 px-2.5 py-2 text-left transition hover:border-gray-300 hover:bg-white dark:border-gray-700/70 dark:bg-gray-900/70 dark:hover:border-gray-600 dark:hover:bg-gray-800"
					title={sourceUrl || getDisplayTitle(decodeString(citation.source?.name ?? ''), 80, 40, 20)}
					on:click={() => {
						showCitationModal = true;
						selectedCitation = citation;
					}}
				>
					<span class="flex size-7 shrink-0 items-center justify-center rounded-md bg-gray-100 dark:bg-gray-800">
						{#if faviconUrl && !faviconFailures[citation.id]}
							<img
								src={faviconUrl}
								alt=""
								class="size-4 rounded-sm"
								on:error={() => hideFavicon(citation.id)}
							/>
						{:else}
							<GlobeAlt className="size-4 text-gray-500" strokeWidth="1.8" />
						{/if}
					</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-xs font-medium text-gray-700 dark:text-gray-200">
							{getDisplayTitle(decodeString(citation.source?.name ?? ''), 64, 36, 18)}
						</span>
						{#if domain}
							<span class="mt-0.5 block truncate text-[11px] text-gray-500 dark:text-gray-400">
								{domain}
							</span>
						{/if}
					</span>
					<span class="shrink-0 text-[10px] font-medium text-gray-400 dark:text-gray-500">
						[{idx + 1}]
					</span>
				</button>
			{/each}
		</div>

		<!-- Expanded source list -->
		{#if showCitations}
			<div
				class="flex flex-col gap-0.5
					bg-white/90 dark:bg-gray-900/90 backdrop-blur-xl
					rounded-xl shadow-lg border border-gray-200/50 dark:border-gray-700/50 p-1"
				style="position: absolute; left: 0; z-index: 20; min-width: 200px; max-width: 320px; max-height: 240px; overflow-y: auto;
					{openAbove ? 'bottom: 100%; margin-bottom: 6px;' : 'top: 100%; margin-top: 6px;'}"
				transition:slide={{ duration: 200, easing: quintOut }}
			>
				{#each citations as citation, idx}
					<button
						id={`source-${id}-${idx + 1}`}
						class="no-toggle outline-hidden flex items-center gap-2 px-2 py-1.5
							rounded-lg hover:bg-gray-50 dark:hover:bg-gray-850 transition
							w-full text-left group"
						on:click={() => {
							showCitationModal = true;
							selectedCitation = citation;
						}}
					>
						<span
							class="flex-shrink-0 size-5 rounded-md bg-gray-100 dark:bg-gray-800
								flex items-center justify-center text-gray-400 dark:text-gray-500"
						>
							{#if isWebCitation(citation)}
								<GlobeAlt className="size-3" strokeWidth="2" />
							{:else}
								<Document className="size-3" strokeWidth="2" />
							{/if}
						</span>
						<span
							class="text-xs text-gray-600 dark:text-gray-300
								group-hover:text-gray-900 dark:group-hover:text-white
								transition truncate flex-1"
						>
							{getDisplayTitle(decodeString(citation.source?.name ?? ''), 60, 30, 20)}
						</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}
