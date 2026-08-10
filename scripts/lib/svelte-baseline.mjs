const DEFAULT_TAIL_LENGTH = 128 * 1024;

export const keepOutputTail = (current, chunk, maxLength = DEFAULT_TAIL_LENGTH) =>
	`${current}${chunk}`.slice(-maxLength);

export const parseSvelteSummary = (output) => {
	const summaries = [
		...output.matchAll(
			/COMPLETED\s+\d+\s+FILES\s+(\d+)\s+ERRORS\s+(\d+)\s+WARNINGS\s+(\d+)\s+FILES_WITH_PROBLEMS/g
		)
	];
	const summary = summaries.at(-1);

	if (!summary) {
		return null;
	}

	return {
		errors: Number.parseInt(summary[1], 10),
		warnings: Number.parseInt(summary[2], 10),
		files: Number.parseInt(summary[3], 10)
	};
};
