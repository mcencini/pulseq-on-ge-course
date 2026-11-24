t0 = tic;
addpath('/tb/pge2'); addpath('/tb/pulseg/third_party'); addpath('/tb/pulseg'); addpath('/tb/pulseq'); addpath('/tb/overlay');
for f = {'DataHash','rmse','MException','throw'}
  if ~exist(f{1}), addpath(['/tb/shims/' f{1}]); fprintf('shim %s\n', f{1}); end
end
warning('off', 'all');
fprintf('[paths %.1f s]\n', toc(t0)); t = tic;
psq = pulseg.fromSeq('/work/gre2d.seq');
fprintf('[fromSeq %.1f s] segments %d, base blocks %d\n', toc(t), psq.nSegments, psq.nParentBlocks); t = tic;
sys_ge = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, 'xrm');
params = pge2.check(psq, sys_ge, 'PNSwt', [1 1 1]);
fprintf('[check %.1f s] b1max %g gmax %g smax %g\n', toc(t), params.b1max, params.gmax, params.smax); t = tic;
seq = mr.Sequence(); seq.read('/work/gre2d.seq');
fprintf('[seq.read %.1f s]\n', toc(t)); t = tic;
ok = pge2.validate(psq, sys_ge, seq, [], 'row', [], 'plot', false);
fprintf('[validate %.1f s] ok=%d\n', toc(t), ok); t = tic;
pge2.serialize(psq, '/work/gre2d.pge', 'pislquant', 10, 'params', params, 'checkHash', false);
d = dir('/work/gre2d.pge');
fprintf('[serialize %.1f s] %d bytes\n', toc(t), d.bytes);
fprintf('[total %.1f s]\n', toc(t0));
