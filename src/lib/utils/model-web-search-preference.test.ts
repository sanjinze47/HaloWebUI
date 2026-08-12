import { describe, expect, it } from 'vitest';

import {
	getModelBuiltinToolPreference,
	getModelBuiltinWebSearchPreference,
	resolveModelBuiltinImageGenerationPreference,
	resolveModelBuiltinWebSearchState,
	resolveSelectedModelBuiltinWebSearchState
} from './model-web-search-preference';

describe('model builtin web search preference', () => {
	it('reads any built-in tool preference from model info metadata', () => {
		expect(
			getModelBuiltinToolPreference(
				{ info: { meta: { builtin_tool_config: { ENABLE_IMAGE_GENERATION_TOOL: false } } } },
				'ENABLE_IMAGE_GENERATION_TOOL'
			)
		).toBe(false);
	});

	it('resolves image-generation defaults across selected models', () => {
		expect(
			resolveModelBuiltinImageGenerationPreference([
				{ info: { meta: { builtin_tool_config: { ENABLE_IMAGE_GENERATION_TOOL: true } } } }
			])
		).toBe(true);
		expect(
			resolveModelBuiltinImageGenerationPreference([
				{ info: { meta: { builtin_tool_config: { ENABLE_IMAGE_GENERATION_TOOL: true } } } },
				{ meta: { builtin_tool_config: { ENABLE_IMAGE_GENERATION_TOOL: false } } }
			])
		).toBe(false);
		expect(resolveModelBuiltinImageGenerationPreference([{ meta: {} }])).toBe(null);
	});

	it('reads explicit preferences from model meta and info meta', () => {
		expect(
			getModelBuiltinWebSearchPreference({
				meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: false } }
			})
		).toBe(false);
		expect(
			getModelBuiltinWebSearchPreference({
				info: { meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: true } } }
			})
		).toBe(true);
		expect(getModelBuiltinWebSearchPreference({ meta: {} })).toBe(null);
	});

	it('lets a single model explicitly disable web search', () => {
		expect(
			resolveModelBuiltinWebSearchState(
				[{ meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: false } } }],
				'native',
				() => 'native'
			)
		).toEqual({ mode: 'off', source: 'model' });
	});

	it('lets any selected model explicitly disable web search', () => {
		expect(
			resolveModelBuiltinWebSearchState(
				[
					{ meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: true } } },
					{ info: { meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: false } } } }
				],
				'halo',
				() => 'auto'
			)
		).toEqual({ mode: 'off', source: 'model' });
	});

	it('uses the enabled mode picker when a model explicitly enables web search', () => {
		expect(
			resolveModelBuiltinWebSearchState(
				[{ info: { meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: true } } } }],
				'off',
				() => 'auto'
			)
		).toEqual({ mode: 'auto', source: 'model' });
	});

	it('retries a pending selection after the model lookup is populated', () => {
		const modelLookup = new Map<string, Record<string, any>>();
		const pickEnabledMode = () => 'native' as const;

		expect(
			resolveSelectedModelBuiltinWebSearchState(
				['grok-model'],
				modelLookup,
				'native',
				pickEnabledMode
			)
		).toBe(null);

		modelLookup.set('grok-model', {
			info: { meta: { builtin_tool_config: { ENABLE_WEB_SEARCH_TOOL: false } } }
		});

		expect(
			resolveSelectedModelBuiltinWebSearchState(
				['grok-model'],
				modelLookup,
				'native',
				pickEnabledMode
			)
		).toEqual({ mode: 'off', source: 'model' });
	});
});
