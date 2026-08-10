export type ImageGenerationResultLayout = {
	columns: number;
	maxWidthPx: number;
	useIntrinsicImageAspectRatio: boolean;
};

const normalizeSlotCount = (slotCount: number) =>
	Math.max(1, Math.min(Math.floor(Number.isFinite(slotCount) ? slotCount : 1), 4));

export const getImageGenerationResultLayout = (
	slotCount: number,
	expandSingleImage = false
): ImageGenerationResultLayout => {
	const normalizedSlotCount = normalizeSlotCount(slotCount);
	const columns = normalizedSlotCount <= 1 ? 1 : normalizedSlotCount === 3 ? 3 : 2;
	const useIntrinsicImageAspectRatio = normalizedSlotCount === 1 && expandSingleImage;
	const maxWidthPx = useIntrinsicImageAspectRatio
		? 720
		: normalizedSlotCount === 1
			? 280
			: normalizedSlotCount === 3
				? 660
				: 560;

	return { columns, maxWidthPx, useIntrinsicImageAspectRatio };
};

export const imageGenerationResultGridStyle = (layout: ImageGenerationResultLayout) =>
	`grid-template-columns: repeat(${layout.columns}, minmax(0, 1fr)); max-width: ${layout.maxWidthPx}px;`;
