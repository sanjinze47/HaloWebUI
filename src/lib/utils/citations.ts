const normalizeCitationList = (value: unknown): any[] => {
	if (Array.isArray(value)) {
		return value;
	}

	if (value === null || value === undefined) {
		return [];
	}

	return [value];
};

const HTTP_URL_PATTERN = /^https?:\/\//i;
const PLACEHOLDER_TITLE_PATTERN = /^\[?\d{1,4}(?:\.\d+)?\]?\.?$/;

export const normalizeCitationUrl = (value: unknown): string => {
	const text = String(value ?? '').trim();
	if (!text) return '';
	if (HTTP_URL_PATTERN.test(text)) return text;

	const embedded = text.match(/https?:\/\/[^\s<>"']+/i)?.[0] ?? '';
	return embedded.replace(/[),.;]+$/, '');
};

export const getCitationSourceUrl = (citation: any): string => {
	const metadata = Array.isArray(citation?.metadata) ? citation.metadata[0] : citation?.metadata;
	const candidates = [citation?.source?.url, metadata?.url, citation?.source?.id, citation?.id];

	for (const candidate of candidates) {
		const url = normalizeCitationUrl(candidate);
		if (url) return url;
	}

	return '';
};

export const getCitationDomain = (citationOrUrl: any): string => {
	const url =
		typeof citationOrUrl === 'string'
			? normalizeCitationUrl(citationOrUrl)
			: getCitationSourceUrl(citationOrUrl);
	if (!url) return '';

	try {
		return new URL(url).hostname.replace(/^www\./i, '');
	} catch {
		return '';
	}
};

export const getCitationFaviconUrl = (citation: any): string => {
	const domain = getCitationDomain(citation);
	return domain
		? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`
		: '';
};

const firstTextValue = (...values: unknown[]): string => {
	for (const value of values) {
		if (typeof value === 'string' && value.trim()) return value.trim();
	}
	return '';
};

export const isPlaceholderCitationTitle = (value: unknown): boolean =>
	PLACEHOLDER_TITLE_PATTERN.test(String(value ?? '').trim());

/** Prefer a useful source label when upstream providers return numeric placeholders. */
export const getCitationDisplayName = (citation: any, fallback = 'Citation source'): string => {
	const metadata = Array.isArray(citation?.metadata) ? citation.metadata[0] : citation?.metadata;
	const rawTitle = firstTextValue(
		citation?.source?.name,
		citation?.source?.title,
		metadata?.name,
		metadata?.title,
		citation?.id
	);

	if (rawTitle && !isPlaceholderCitationTitle(rawTitle)) {
		const titleUrl = normalizeCitationUrl(rawTitle);
		return titleUrl ? getCitationDomain(titleUrl) || rawTitle : rawTitle;
	}
	return getCitationDomain(citation) || normalizeCitationUrl(rawTitle) || fallback;
};

export const hasUsefulCitationExcerpt = (document: unknown, title = ''): boolean => {
	const text = String(document ?? '').trim();
	if (!text || isPlaceholderCitationTitle(text)) return false;

	const normalizedText = text.replace(/\s+/g, ' ').toLowerCase();
	const normalizedTitle = String(title ?? '')
		.trim()
		.replace(/\s+/g, ' ')
		.toLowerCase();
	return !normalizedTitle || normalizedText !== normalizedTitle;
};

export const getCitationDocuments = (citation: any): any[] => {
	return normalizeCitationList(citation?.document ?? citation?.documents);
};

export const getCitationMetadata = (citation: any): any[] => {
	return normalizeCitationList(citation?.metadata);
};

export const getCitationDistances = (citation: any): any[] => {
	return normalizeCitationList(citation?.distances);
};

const getMetadataFallbackDocument = (metadata: any): string => {
	if (!metadata || typeof metadata !== 'object') {
		return '';
	}

	const candidates = [metadata.content, metadata.snippet, metadata.text, metadata.summary];
	for (const candidate of candidates) {
		if (typeof candidate === 'string' && candidate.trim()) {
			return candidate;
		}
	}

	return '';
};

export const getCitationEntries = (citation: any) => {
	const documents = getCitationDocuments(citation);
	const metadata = getCitationMetadata(citation);
	const distances = getCitationDistances(citation);

	const entryCount = Math.max(
		documents.length,
		metadata.length,
		distances.length,
		citation?.source ? 1 : 0
	);

	return Array.from({ length: entryCount }, (_, index) => {
		const document = documents[index];
		const documentText = typeof document === 'string' ? document : `${document ?? ''}`;

		return {
			document: documentText.trim() ? documentText : getMetadataFallbackDocument(metadata[index]),
			metadata: metadata[index],
			distance: distances[index]
		};
	});
};

export const getCitationSourceUrls = (citations: unknown): string[] => {
	const urls = new Set<string>();

	normalizeCitationList(citations).forEach((citation) => {
		if (!citation || typeof citation !== 'object') return;

		const addUrl = (value: unknown) => {
			const url = normalizeCitationUrl(value);
			if (url) urls.add(url);
		};

		addUrl(getCitationSourceUrl(citation));
		getCitationEntries(citation).forEach(({ metadata }) => {
			addUrl(metadata?.url);
			addUrl(metadata?.link);
			addUrl(metadata?.source);
		});
	});

	return [...urls];
};

export const getCitationUrlKey = (value: unknown): string => {
	const normalized = normalizeCitationUrl(value);
	if (!normalized) return '';

	try {
		const url = new URL(normalized);
		const search = [...url.searchParams]
			.filter(([key]) => !/^(utm_|gclid$|fbclid$)/i.test(key))
			.sort(([left], [right]) => left.localeCompare(right))
			.map(([key, item]) => `${encodeURIComponent(key)}=${encodeURIComponent(item)}`)
			.join('&');
		const path = url.pathname.replace(/\/+$/, '') || '/';
		return `${url.origin}${path}${search ? `?${search}` : ''}`.toLowerCase();
	} catch {
		return normalized.toLowerCase();
	}
};
