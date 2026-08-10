import {Config} from '@remotion/cli/config';
import os from 'os';

Config.setVideoImageFormat('jpeg');
Config.overrideWebpackConfig((c) => c);

/**
 * Use every core. Remotion's default leaves most of the machine idle: measured
 * on an 8-core box, a 288-frame render took 183s at the default and 104s at
 * --concurrency=8 — 1.76x, for one line of config.
 *
 * Do NOT reach for --gl=angle to go faster. Measured on the same render it made
 * things WORSE (156s vs 104s): this composition is video-decode and layout
 * bound, not GPU bound, so the ANGLE path adds overhead and buys nothing.
 */
Config.setConcurrency(Math.max(1, os.cpus().length));
