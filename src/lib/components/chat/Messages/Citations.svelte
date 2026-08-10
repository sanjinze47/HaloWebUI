<script lang="ts">
	import { getContext } from 'svelte';
	import { Eye, EyeOff } from 'lucide-svelte';
	import CitationsModal from './CitationsModal.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import {
		getCitationDomain,
		getCitationEntries,
		getCitationFaviconUrl,
		getCitationSourceUrl
	} from '$lib/utils/citations';
	import { getDisplayTitle, decodeString } from '$lib/utils/marked/citation-extension';
	import { translateWithDefault } from '$lib/i18n';

	const i18n: any = getContext('i18n');
	const tr = (key: string, defaultValue: string, options: Record<string, any> = {}) =>
		translateWithDefault($i18n, key, defaultValue, options);

	type Citation = {
		id: string;
		source?: Record<string, any>;
		document: string[];
		metadata: any[];
		distances: number[];
	};

	export let id = '';
	export let sources: Record<string, any>[] = [];
	export let inlineCitationsVisible = true;
	export let onToggleInlineCitations: (() => void) | null = null;

	let citations: Citation[] = [];
	let showPercentage = false;
	let showRelevance = true;
	let showCitationDrawer = false;
	let selectedCitation: Citation | null = null;
	let faviconFailures: Record<string, boolean> = {};

	function calculateShowRelevance(items: any[]) {
		const distances = items.flatMap((citation) => citation.distances ?? []);
		const inRange = distances.filter((d) => d !== undefined && d >= -1 && d <= 1).length;
		const outOfRange = distances.filter((d) => d !== undefined && (d < -1 || d > 1)).length;

		if (distances.length === 0) return false;
		if (
			(inRange === distances.length - 1 && outOfRange === 1) ||
			(outOfRange === distances.length - 1 && inRange === 1)
		) {
			return false;
		}

		return true;
	}

	function shouldShowPercentage(items: any[]) {
		const distances = items.flatMap((citation) => citation.distances ?? []);
		return distances.every((d) => d !== undefined && d >= -1 && d <= 1);
	}

	function isWebCitation(citation: Citation): boolean {
		return Boolean(getCitationSourceUrl(citation));
	}

	function getCitationTitle(citation: Citation, limit = 64): string {
		return getDisplayTitle(
			decodeString(citation.source?.name ?? citation.source?.title ?? citation.id ?? ''),
			limit,
			36,
			18
		);
	}

	function hideFavicon(citationId: string) {
		faviconFailures = { ...faviconFailures, [citationId]: true };
	}

	function openCitation(citation: Citation) {
		selectedCitation = citation;
		showCitationDrawer = true;
	}

	function openAllCitations() {
		if (citations.length > 0) {
			openCitation(selectedCitation ?? citations[0]);
		}
	}

	$: {
		citations = sources.reduce<Citation[]>((acc, source) => {
			if (!source || typeof source !== 'object' || Object.keys(source).length === 0) {
				return acc;
			}

			getCitationEntries(source).forEach(({ document, metadata, distance }) => {
				const documentText = typeof document === 'string' ? document : `${document ?? ''}`;
				const sourceRecord =
					source.source && typeof source.source === 'object' ? { ...source.source } : {};
				const sourceId = String(metadata?.source ?? sourceRecord.id ?? source.id ?? 'N/A');
				const metadataUrl = metadata?.url ?? metadata?.link ?? '';
				const sourceUrl = getCitationSourceUrl({
					id: sourceId,
					metadata: { url: metadataUrl },
					source: sourceRecord
				});

				if (metadata?.name) sourceRecord.name = metadata.name;
				if (metadataUrl && !sourceRecord.url) sourceRecord.url = metadataUrl;
				if (sourceUrl && !sourceRecord.url) sourceRecord.url = sourceUrl;
				if (sourceUrl && !sourceRecord.name) sourceRecord.name = sourceUrl;

				const existingSource = acc.find((item) => item.id === sourceId);
				if (existingSource) {
					existingSource.document.push(documentText);
					existingSource.metadata.push(metadata);
					if (distance !== undefined) existingSource.distances.push(distance);
				} else {
					acc.push({
						id: sourceId,
						source: sourceRecord,
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
		if (selectedCitation && !citations.some((citation) => citation.id === selectedCitation?.id)) {
			selectedCitation = citations[0] ?? null;
		}
	}

	function normalizeCitationIndex(
		indexOrIdentifier: number | string | null | undefined
	): number | null {
		if (typeof indexOrIdentifier === 'number' && Number.isInteger(indexOrIdentifier)) {
			return indexOrIdentifier;
		}

		if (typeof indexOrIdentifier === 'string') {
			const match = indexOrIdentifier.match(/^(\d+)/);
			if (match) return Number.parseInt(match[1], 10);
		}

		return null;
	}

	export function openCitationByIndex(
		indexOrIdentifier: number | string | null | undefined
	): boolean {
		const index = normalizeCitationIndex(indexOrIdentifier);
		if (index === null || index < 1) return false;

		const citation = citations[index - 1];
		if (!citation) return false;

		openCitation(citation);
		return true;
	}
</script>

<CitationsModal
	bind:show={showCitationDrawer}
	citation={selectedCitation}
	{citations}
	{showPercentage}
	{showRelevance}
/>

{#if citations.length > 0}
	{@const hasWebCitations = citations.some(isWebCitation)}
	<div class="-mx-0.5 mt-1.5 w-full">
		<div class="flex min-h-[30px] items-center justify-between gap-3 text-xs">
			<div class="flex min-w-0 items-center gap-2">
				{#if onToggleInlineCitations}
					<Tooltip
						content={inlineCitationsVisible
							? tr('隐藏正文引用标签', 'Hide inline citations')
							: tr('显示正文引用标签', 'Show inline citations')}
						placement="bottom"
					>
						<button
							type="button"
							class="flex size-6 items-center justify-center rounded-md text-gray-400 transition hover:bg-black/5 hover:text-gray-700 dark:text-gray-500 dark:hover:bg-white/5 dark:hover:text-gray-200"
							aria-label={inlineCitationsVisible
								? tr('隐藏正文引用标签', 'Hide inline citations')
								: tr('显示正文引用标签', 'Show inline citations')}
							on:click={onToggleInlineCitations}
						>
							{#if inlineCitationsVisible}
								<EyeOff className="size-3.5" strokeWidth={2.1} />
							{:else}
								<Eye className="size-3.5" strokeWidth={2.1} />
							{/if}
						</button>
					</Tooltip>
				{/if}
				<div class="flex min-w-0 items-center gap-1.5 font-medium text-gray-500 dark:text-gray-400">
					{#if hasWebCitations}
						<GlobeAlt className="size-3.5 shrink-0" strokeWidth="1.9" />
					{:else}
						<Document className="size-3.5 shrink-0" strokeWidth="1.9" />
					{/if}
					<span>{tr('来源', 'Sources')}</span>
					<span class="text-gray-400 dark:text-gray-500">{citations.length}</span>
				</div>
			</div>
			<button
				type="button"
				class="shrink-0 rounded-md px-1.5 py-1 text-[11px] font-medium text-blue-600 transition hover:bg-black/5 dark:text-blue-400 dark:hover:bg-white/5"
				on:click={openAllCitations}
			>
				{tr('查看全部', 'View all')}
			</button>
		</div>

		<div
			class="flex w-full overflow-x-auto border-y border-black/5 scrollbar-none dark:border-white/5"
		>
			{#each citations.slice(0, 8) as citation, idx}
				{@const sourceUrl = getCitationSourceUrl(citation)}
				{@const domain = getCitationDomain(citation)}
				{@const faviconUrl = getCitationFaviconUrl(citation)}
				<button
					type="button"
					id={`source-${id}-${idx + 1}`}
					class="group flex min-w-[168px] max-w-[230px] flex-1 shrink-0 items-center gap-2 border-r border-black/5 px-2.5 py-2 text-left transition hover:bg-black/[0.035] dark:border-white/5 dark:hover:bg-white/[0.035] first:pl-0"
					title={sourceUrl || getCitationTitle(citation, 80)}
					on:click={() => openCitation(citation)}
				>
					<span
						class="flex size-5 shrink-0 items-center justify-center overflow-hidden rounded bg-gray-100 dark:bg-gray-800"
					>
						{#if faviconUrl && !faviconFailures[citation.id]}
							<img
								src={faviconUrl}
								alt=""
								class="size-4 rounded-sm"
								on:error={() => hideFavicon(citation.id)}
							/>
						{:else if isWebCitation(citation)}
							<GlobeAlt className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
						{:else}
							<Document className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
						{/if}
					</span>
					<span class="min-w-0 flex-1">
						<span
							class="block truncate text-[11px] font-medium text-gray-700 group-hover:text-gray-950 dark:text-gray-200 dark:group-hover:text-white"
						>
							{idx + 1}. {getCitationTitle(citation)}
						</span>
						{#if domain}
							<span class="mt-0.5 block truncate text-[10px] text-gray-400 dark:text-gray-500">
								{domain}
							</span>
						{/if}
					</span>
				</button>
			{/each}
			{#if citations.length > 8}
				<button
					type="button"
					class="flex min-w-[72px] shrink-0 items-center justify-center px-2 text-[11px] font-medium text-blue-600 transition hover:bg-black/[0.035] dark:text-blue-400 dark:hover:bg-white/[0.035]"
					on:click={openAllCitations}
				>
					+{citations.length - 8}
				</button>
			{/if}
		</div>
	</div>
{/if}
