<script lang="ts">
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { BookOpen, Copy, ExternalLink, X } from 'lucide-svelte';
	import Drawer from '$lib/components/common/Drawer.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Document from '$lib/components/icons/Document.svelte';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { mobile, settings } from '$lib/stores';
	import { copyToClipboard } from '$lib/utils';
	import {
		getCitationDomain,
		getCitationDisplayName,
		getCitationEntries,
		getCitationFaviconUrl,
		getCitationSourceUrl,
		hasUsefulCitationExcerpt,
		normalizeCitationUrl
	} from '$lib/utils/citations';
	import { translateWithDefault } from '$lib/i18n';
	import {
		decodeString,
		getDisplayTitle,
		getTextFragmentUrl
	} from '$lib/utils/marked/citation-extension';
	import Markdown from './Markdown.svelte';

	const i18n: any = getContext('i18n');
	const tr = (key: string, defaultValue: string, options: Record<string, any> = {}) =>
		translateWithDefault($i18n, key, defaultValue, options);

	export let show = false;
	export let citation: Record<string, any> | null = null;
	export let citations: Record<string, any>[] = [];
	export let showPercentage = false;
	export let showRelevance = true;

	let mergedDocuments: Array<{
		source?: Record<string, any>;
		document: string;
		metadata: Record<string, any>;
		distance?: number;
	}> = [];
	let faviconFailures: Record<string, boolean> = {};

	function calculatePercentage(distance: number) {
		if (typeof distance !== 'number') return null;
		if (distance < 0) return 0;
		if (distance > 1) return 100;
		return Math.round(distance * 10000) / 100;
	}

	function getRelevanceColor(percentage: number) {
		if (percentage >= 80)
			return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
		if (percentage >= 60)
			return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300';
		if (percentage >= 40)
			return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300';
		return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
	}

	function getCitationTitle(item: Record<string, any> | null, limit = 90): string {
		return getDisplayTitle(
			decodeString(getCitationDisplayName(item, tr('引用来源', 'Citation source'))),
			limit,
			44,
			22
		);
	}

	function hasVisibleExcerpt(document: (typeof mergedDocuments)[number]): boolean {
		return hasUsefulCitationExcerpt(document.document, getCitationTitle(citation));
	}

	function getDocumentUrl(document: any): string {
		if (document?.metadata?.file_id) {
			return `${WEBUI_API_BASE_URL}/files/${document.metadata.file_id}/content${
				document?.metadata?.page !== undefined ? `#page=${document.metadata.page + 1}` : ''
			}`;
		}

		return normalizeCitationUrl(
			document?.metadata?.url ?? document?.metadata?.link ?? document?.source?.url
		);
	}

	function getPrimarySourceUrl(): string {
		return getDocumentUrl(mergedDocuments[0]) || getCitationSourceUrl(citation);
	}

	function getSourceDate(document: any): string {
		return String(
			document?.metadata?.published_at ??
				document?.metadata?.publishedAt ??
				document?.metadata?.date ??
				document?.metadata?.updated_at ??
				''
		).trim();
	}

	function hideFavicon(citationId: string) {
		faviconFailures = { ...faviconFailures, [citationId]: true };
	}

	async function copySourceLink() {
		const sourceUrl = getPrimarySourceUrl();
		if (!sourceUrl) return;

		if (await copyToClipboard(sourceUrl)) {
			toast.success(tr('链接已复制', 'Link copied'));
		} else {
			toast.error(tr('复制链接失败', 'Failed to copy link'));
		}
	}

	$: if (!citation && citations.length > 0) {
		citation = citations[0];
	}

	$: if (citation) {
		mergedDocuments = getCitationEntries(citation).map(({ document, metadata, distance }) => ({
			source: citation?.source,
			document: typeof document === 'string' ? document : `${document ?? ''}`,
			metadata: metadata ?? {},
			distance
		}));

		if (mergedDocuments.every((document) => document.distance !== undefined)) {
			mergedDocuments = mergedDocuments.sort(
				(a, b) =>
					(b.distance ?? Number.NEGATIVE_INFINITY) - (a.distance ?? Number.NEGATIVE_INFINITY)
			);
		}
	} else {
		mergedDocuments = [];
	}
</script>

<Drawer
	placement={$mobile ? 'bottom' : 'right'}
	bind:show
	className={$mobile
		? 'h-[86dvh] max-h-[720px] w-full overflow-hidden rounded-t-xl bg-white dark:bg-gray-900'
		: 'h-full w-full max-w-[680px] overflow-hidden bg-white dark:bg-gray-900'}
	overlayClassName="bg-black/25 dark:bg-black/40"
>
	<div
		class="flex h-full min-h-0 flex-col"
		role="dialog"
		aria-modal="true"
		aria-labelledby="citation-drawer-title"
	>
		{#if $mobile}
			<div
				class="mx-auto mt-2 h-1 w-10 rounded-full bg-gray-300 dark:bg-gray-700"
				aria-hidden="true"
			></div>
		{/if}
		<header
			class="flex h-16 shrink-0 items-center justify-between border-b border-black/5 px-4 dark:border-white/5 md:px-5"
		>
			<div class="flex min-w-0 items-center gap-2.5">
				<BookOpen class="size-4 shrink-0 text-gray-500 dark:text-gray-400" strokeWidth={1.9} />
				<div class="min-w-0">
					<div
						id="citation-drawer-title"
						class="truncate text-sm font-semibold text-gray-900 dark:text-gray-100"
					>
						{tr('引用来源', 'Citation sources')}
					</div>
					<div class="text-[10px] text-gray-400 dark:text-gray-500">
						{tr('共 {{count}} 项', '{{count}} sources', { count: citations.length })}
					</div>
				</div>
			</div>
			<button
				type="button"
				class="flex size-8 shrink-0 items-center justify-center rounded-md text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-white"
				aria-label={tr('关闭', 'Close')}
				title={tr('关闭', 'Close')}
				on:click={() => (show = false)}
			>
				<X class="size-4" strokeWidth={2} />
			</button>
		</header>

		<div
			class="grid min-h-0 flex-1 grid-rows-[112px_minmax(0,1fr)] md:grid-cols-[224px_minmax(0,1fr)] md:grid-rows-1"
		>
			<nav
				class="flex min-w-0 gap-1 overflow-x-auto border-b border-black/5 bg-gray-50/70 p-2 scrollbar-thin dark:border-white/5 dark:bg-gray-950/30 md:flex-col md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r"
				aria-label={tr('来源列表', 'Source list')}
			>
				{#each citations as item, idx}
					{@const domain = getCitationDomain(item)}
					{@const faviconUrl = getCitationFaviconUrl(item)}
					{@const selected = item.id === citation?.id}
					<button
						type="button"
						class="relative grid min-h-[48px] min-w-[158px] grid-cols-[20px_minmax(0,1fr)] items-center gap-2 rounded-md px-2 py-1.5 text-left transition hover:bg-black/5 dark:hover:bg-white/5 md:min-w-0 {selected
							? 'bg-black/5 shadow-[inset_2px_0_0_0_rgba(16,185,129,0.85)] dark:bg-white/5'
							: ''}"
						aria-current={selected ? 'true' : undefined}
						on:click={() => (citation = item)}
					>
						<span
							class="flex size-5 items-center justify-center overflow-hidden rounded bg-gray-100 dark:bg-gray-800"
						>
							{#if faviconUrl && !faviconFailures[item.id]}
								<img
									src={faviconUrl}
									alt=""
									class="size-4 rounded-sm"
									on:error={() => hideFavicon(item.id)}
								/>
							{:else if getCitationSourceUrl(item)}
								<GlobeAlt className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
							{:else}
								<Document className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
							{/if}
						</span>
						<span class="min-w-0">
							<span class="block truncate text-[11px] font-medium text-gray-700 dark:text-gray-200">
								{idx + 1}. {getCitationTitle(item, 58)}
							</span>
							<span class="mt-0.5 block truncate text-[10px] text-gray-400 dark:text-gray-500">
								{domain || tr('本地文档', 'Local document')}
							</span>
						</span>
					</button>
				{/each}
			</nav>

			<section
				class="min-h-0 min-w-0 overflow-y-auto bg-white px-4 py-5 scrollbar-thin dark:bg-gray-900 md:px-6"
			>
				{#if citation}
					{@const sourceIndex = Math.max(
						0,
						citations.findIndex((item) => item.id === citation?.id)
					)}
					{@const sourceUrl = getPrimarySourceUrl()}
					{@const sourceDomain = getCitationDomain(sourceUrl || citation)}
					{@const faviconUrl = getCitationFaviconUrl(citation)}
					{@const firstDocument = mergedDocuments[0]}
					<div class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
						<span
							class="flex size-5 items-center justify-center overflow-hidden rounded bg-gray-100 dark:bg-gray-800"
						>
							{#if faviconUrl && !faviconFailures[`detail-${citation.id}`]}
								<img
									src={faviconUrl}
									alt=""
									class="size-4 rounded-sm"
									on:error={() => hideFavicon(`detail-${citation?.id ?? ''}`)}
								/>
							{:else if sourceUrl}
								<GlobeAlt className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
							{:else}
								<Document className="size-3.5 text-gray-400 dark:text-gray-500" strokeWidth="1.8" />
							{/if}
						</span>
						<span class="min-w-0 truncate">{sourceDomain || tr('本地文档', 'Local document')}</span>
						<span aria-hidden="true">·</span>
						<span class="shrink-0"
							>{tr('来源 {{index}}', 'Source {{index}}', { index: sourceIndex + 1 })}</span
						>
					</div>

					<h2 class="mt-3 text-lg font-semibold leading-7 text-gray-900 dark:text-gray-100">
						{#if sourceUrl}
							<a
								href={sourceUrl}
								target="_blank"
								rel="noopener noreferrer nofollow"
								class="transition hover:text-blue-600 dark:hover:text-blue-400"
							>
								{getCitationTitle(citation)}
							</a>
						{:else}
							{getCitationTitle(citation)}
						{/if}
					</h2>

					<div
						class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-gray-400 dark:text-gray-500"
					>
						{#if getSourceDate(firstDocument)}
							<span>{getSourceDate(firstDocument)}</span>
						{/if}
						{#if Number.isInteger(firstDocument?.metadata?.page)}
							<span
								>{tr('第 {{page}} 页', 'Page {{page}}', {
									page: firstDocument.metadata.page + 1
								})}</span
							>
						{/if}
					</div>

					<div class="mt-4 flex flex-wrap gap-2">
						{#if sourceUrl}
							<a
								href={sourceUrl}
								target="_blank"
								rel="noopener noreferrer nofollow"
								class="flex h-8 items-center gap-1.5 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 text-[11px] font-medium text-emerald-700 transition hover:bg-emerald-500/15 dark:text-emerald-300"
							>
								<ExternalLink class="size-3.5" strokeWidth={1.9} />
								<span>{tr('打开原文', 'Open source')}</span>
							</a>
							<button
								type="button"
								class="flex h-8 items-center gap-1.5 rounded-md border border-black/10 px-2.5 text-[11px] font-medium text-gray-700 transition hover:bg-black/5 dark:border-white/10 dark:text-gray-200 dark:hover:bg-white/5"
								on:click={copySourceLink}
							>
								<Copy class="size-3.5" strokeWidth={1.9} />
								<span>{tr('复制链接', 'Copy link')}</span>
							</button>
						{/if}
					</div>

					{#if sourceUrl}
						<details
							class="mt-4 rounded-md border border-black/5 bg-black/[0.02] px-3 py-2 dark:border-white/5 dark:bg-white/[0.02]"
						>
							<summary
								class="cursor-pointer text-[11px] font-medium text-gray-500 dark:text-gray-400"
							>
								{tr('查看链接', 'View link')}
							</summary>
							<div
								class="mt-2 break-all font-mono text-[10px] leading-4 text-gray-400 dark:text-gray-500"
							>
								{sourceUrl}
							</div>
						</details>
					{/if}

					{@const excerptDocuments = mergedDocuments.filter(hasVisibleExcerpt)}
					{#if excerptDocuments.length > 0}
						<div class="mt-6 border-t border-black/5 pt-4 dark:border-white/5">
							<div
								class="mb-3 text-[10px] font-semibold uppercase text-gray-400 dark:text-gray-500"
							>
								{tr('引用片段', 'Cited excerpt')}
							</div>

							{#each excerptDocuments as document, documentIdx}
								<div
									class="mb-4 last:mb-0 rounded-lg border border-black/10 bg-black/[0.02] p-3 dark:border-white/10 dark:bg-white/[0.025]"
								>
									<div
										class="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500"
									>
										{#if showRelevance && document.distance !== undefined}
											{#if showPercentage}
												{@const percentage = calculatePercentage(document.distance)}
												{#if typeof percentage === 'number'}
													<span
														class={`rounded px-1.5 py-0.5 font-medium ${getRelevanceColor(percentage)}`}
													>
														{tr('相关度 {{percentage}}%', 'Relevance {{percentage}}%', {
															percentage: percentage.toFixed(2)
														})}
													</span>
												{/if}
											{:else}
												<span>{document.distance.toFixed(4)}</span>
											{/if}
										{/if}
										{#if Number.isInteger(document.metadata?.page)}
											<span
												>{tr('第 {{page}} 页', 'Page {{page}}', {
													page: document.metadata.page + 1
												})}</span
											>
										{/if}
										{#if document.source?.url?.includes('http') && getTextFragmentUrl(document)}
											<a
												href={getTextFragmentUrl(document)}
												target="_blank"
												rel="noopener noreferrer nofollow"
												class="text-blue-600 hover:underline dark:text-blue-400"
											>
												{tr('定位原文', 'Open passage')}
											</a>
										{/if}
									</div>

									<div
										class="max-h-[280px] overflow-y-auto border-l-2 border-emerald-500/70 pl-3 text-sm leading-6 text-gray-600 dark:text-gray-300"
									>
										{#if document.metadata?.html}
											<iframe
												class="h-auto w-full border-0"
												sandbox="allow-scripts allow-forms{($settings?.iframeSandboxAllowSameOrigin ??
												false)
													? ' allow-same-origin'
													: ''}"
												srcdoc={document.document}
												title={tr('引用内容', 'Citation content')}
											></iframe>
										{:else if $settings?.renderMarkdownInPreviews ?? true}
											<div class="markdown-prose text-sm">
												<Markdown
													id={`citation-${documentIdx}`}
													content={document.document?.trim()?.replace(/\n\n+/g, '\n\n') ?? ''}
												/>
											</div>
										{:else}
											<pre
												class="whitespace-pre-wrap font-sans text-sm leading-6">{document.document
													.trim()
													.replace(/\n\n+/g, '\n\n')}</pre>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				{:else}
					<div
						class="flex h-full items-center justify-center text-sm text-gray-400 dark:text-gray-500"
					>
						{tr('暂无引用来源', 'No citation source available')}
					</div>
				{/if}
			</section>
		</div>
	</div>
</Drawer>
