"use client";

import { useEffect, useRef } from "react";

// A slow field of teal and indigo drifting over near-black, with the faint
// coordinate grid that every 3blue1brown scene is drawn on. Written by hand
// rather than pulled from a library: it is one fragment shader and a quad.
//
// Contrast is deliberately low. The background is behind text on every page,
// so it has to read as texture, not as content.

const VERTEX = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision mediump float;
uniform vec2 u_res;
uniform float u_time;

// Cheap hash-based value noise. Good enough for a background; far cheaper
// than simplex, and it is running on every pixel every frame.
float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 5; i++) {
    v += amp * noise(p);
    p = p * 2.03 + vec2(17.0, 9.0);
    amp *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  vec2 p = (gl_FragCoord.xy - 0.5 * u_res) / u_res.y;
  float t = u_time * 0.035;

  // Two layers of domain-warped noise, drifting in different directions,
  // so the field breathes rather than scrolls.
  vec2 q = vec2(fbm(p * 1.6 + t), fbm(p * 1.6 - t * 0.7 + 3.1));
  float f = fbm(p * 1.9 + 1.4 * q + vec2(t * 0.5, -t * 0.3));

  vec3 bg     = vec3(0.055, 0.067, 0.086);   // #0e1116
  vec3 indigo = vec3(0.16, 0.19, 0.42);
  vec3 teal   = vec3(0.345, 0.769, 0.867);   // #58c4dd
  vec3 warm   = vec3(0.788, 0.545, 0.42);    // #c98b6b

  vec3 col = bg;
  col = mix(col, indigo, smoothstep(0.35, 0.85, f) * 0.35);
  col = mix(col, teal,   smoothstep(0.55, 0.95, f) * 0.22);
  // A rare warm fleck, the "1brown".
  col = mix(col, warm,   smoothstep(0.82, 1.0, fbm(p * 3.0 - t)) * 0.10);

  // The coordinate grid. Thin, faint, drifting very slowly.
  vec2 g = fract((p + vec2(t * 0.15, t * 0.08)) * 6.0);
  float line = min(min(g.x, 1.0 - g.x), min(g.y, 1.0 - g.y));
  float grid = 1.0 - smoothstep(0.0, 0.012, line);
  col += teal * grid * 0.045;

  // Vignette, so the edges fall away and the centre reads first.
  float vig = smoothstep(1.25, 0.35, length(p));
  col = mix(bg, col, vig);

  gl_FragColor = vec4(col, 1.0);
}
`;

export function ShaderBackground() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { antialias: false, alpha: false });
    if (!gl) return; // the CSS background underneath is the fallback

    const compile = (type: number, src: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, src);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.warn(gl.getShaderInfoLog(shader));
        return null;
      }
      return shader;
    };
    const vs = compile(gl.VERTEX_SHADER, VERTEX);
    const fs = compile(gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vs || !fs) return;

    const program = gl.createProgram()!;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.useProgram(program);

    const quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const aPos = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(program, "u_res");
    const uTime = gl.getUniformLocation(program, "u_time");

    // Render below native resolution: this is soft texture, and pixels here
    // are the most expensive thing on the page.
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.25) * 0.75;
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    let frame = 0;

    const draw = () => {
      gl.uniform1f(uTime, (performance.now() - start) / 1000);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      // One still frame for reduced motion; otherwise keep going while visible.
      if (!reduced && !document.hidden) frame = requestAnimationFrame(draw);
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden) frame = requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", onVisibility);
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
      gl.deleteProgram(program);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
    />
  );
}
