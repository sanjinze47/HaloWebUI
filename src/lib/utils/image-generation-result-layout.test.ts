import { describe, expect, it } from 'vitest';

import {
	getImageGenerationResultLayout,
	imageGenerationResultGridStyle
} from './image-generation-result-layout';

describe('image generation result layout', () => {
	it('shows a successful single image at its intrinsic aspect ratio', () => {
		const layout = getImageGenerationResultLayout(1, true);

		expect(layout).toEqual({
			columns: 1,
			maxWidthPx: 720,
			useIntrinsicImageAspectRatio: true
		});
		expect(imageGenerationResultGridStyle(layout)).toContain('max-width: 720px');
	});

	it('keeps single placeholders and failures compact', () => {
		expect(getImageGenerationResultLayout(1)).toEqual({
			columns: 1,
			maxWidthPx: 280,
			useIntrinsicImageAspectRatio: false
		});
	});

	it.each([
		[2, 2, 560],
		[3, 3, 660],
		[4, 2, 560]
	])('keeps the %i-image result grid stable', (slotCount, columns, maxWidthPx) => {
		expect(getImageGenerationResultLayout(slotCount, true)).toEqual({
			columns,
			maxWidthPx,
			useIntrinsicImageAspectRatio: false
		});
	});
});
