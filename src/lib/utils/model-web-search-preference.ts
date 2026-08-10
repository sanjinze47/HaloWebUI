import type { Model } from '$lib/stores';
import type { WebSearchMode, WebSearchModeSource } from './web-search-mode';

export type ModelWebSearchState = {
	mode: WebSearchMode;
	source: WebSearchModeSource;
};

export const getModelBuiltinWebSearchPreference = (
	model: Model | Record<string, any> | null | undefined
): boolean | null => {
	const value =
		(model as any)?.info?.meta?.builtin_tool_config?.ENABLE_WEB_SEARCH_TOOL ??
		(model as any)?.meta?.builtin_tool_config?.ENABLE_WEB_SEARCH_TOOL;

	return typeof value === 'boolean' ? value : null;
};

export const resolveModelBuiltinWebSearchState = (
	selectedModels: (Model | Record<string, any>)[],
	fallbackMode: WebSearchMode,
	pickEnabledMode: (selectedModels: Model[]) => WebSearchMode
): ModelWebSearchState => {
	if (selectedModels.length === 0) {
		return { mode: fallbackMode, source: 'default' };
	}

	const preferences = selectedModels.map(getModelBuiltinWebSearchPreference);
	if (preferences.some((value) => value === false)) {
		return { mode: 'off', source: 'model' };
	}

	if (preferences.some((value) => value === true)) {
		return {
			mode: pickEnabledMode(selectedModels as Model[]),
			source: 'model'
		};
	}

	return { mode: fallbackMode, source: 'default' };
};

/**
 * Resolve a selection against the current model lookup before applying model defaults.
 * A null result means the model list is still incomplete and the caller should retry.
 */
export const resolveSelectedModelBuiltinWebSearchState = (
	selectedModelIds: unknown[],
	modelLookup: ReadonlyMap<string, Model | Record<string, any>>,
	fallbackMode: WebSearchMode,
	pickEnabledMode: (selectedModels: Model[]) => WebSearchMode
): ModelWebSearchState | null => {
	const requestedIds = selectedModelIds.filter(
		(id): id is string => typeof id === 'string' && id.trim() !== ''
	);
	const resolvedModels = requestedIds
		.map((id) => modelLookup.get(id))
		.filter((model): model is Model | Record<string, any> => Boolean(model));

	if (requestedIds.length > 0 && resolvedModels.length !== requestedIds.length) {
		return null;
	}

	return resolveModelBuiltinWebSearchState(resolvedModels, fallbackMode, pickEnabledMode);
};
