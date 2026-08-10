const fs = require('node:fs');

const summaryPattern = /\s(?:COMPLETED|FAILURE)\s/;

process.stdout.write = (chunk, encoding, callback) => {
	const chunkEncoding = typeof encoding === 'string' ? encoding : undefined;
	const onComplete = typeof encoding === 'function' ? encoding : callback;
	const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk, chunkEncoding);

	if (summaryPattern.test(buffer.toString('utf8'))) {
		fs.writeSync(process.stdout.fd, buffer);
	}
	if (typeof onComplete === 'function') {
		queueMicrotask(onComplete);
	}

	return true;
};
