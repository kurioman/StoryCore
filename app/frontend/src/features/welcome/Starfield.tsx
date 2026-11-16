// Animated starfield behind the welcome page (v1.8). One <canvas>, no images: stars twinkle, drift a little, follow
// the mouse with a slight parallax, and can be drawn towards a point (the "Start" button on hover) before slowly
// returning home. With "reduce motion" switched on in the system, the stars are drawn once and stay still.
import * as React from "react";

export type StarfieldHandle = {
  /** Draw nearby stars towards this point (page coordinates), or release them with null. */
  setAttractor: (point: { x: number; y: number } | null) => void;
};

type Star = {
  hx: number; // home position, 0..1 of the canvas
  hy: number;
  x: number; // current offset from home, in px (attraction)
  y: number;
  z: number; // depth 0.25..1: size, brightness and parallax
  r: number;
  phase: number;
  speed: number;
  drift: number;
  color: string;
  sparkle: boolean;
};

type Comet = { x: number; y: number; vx: number; vy: number; life: number };

const COLORS = ["#f6d98f", "#e9c477", "#fff3cf", "#d9ae5f", "#ffe6a6"];
const ATTRACT_RADIUS = 300;

function makeStars(width: number, height: number): Star[] {
  const count = Math.max(90, Math.min(380, Math.round((width * height) / 5200)));
  const stars: Star[] = [];
  for (let i = 0; i < count; i++) {
    const z = 0.25 + Math.random() ** 1.6 * 0.75;
    stars.push({
      hx: Math.random(),
      hy: Math.random(),
      x: 0,
      y: 0,
      z,
      r: 0.5 + z * 1.5 + (Math.random() < 0.05 ? 0.9 : 0),
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.8,
      drift: Math.random() * Math.PI * 2,
      color: COLORS[(Math.random() * COLORS.length) | 0],
      sparkle: Math.random() < 0.09,
    });
  }
  return stars;
}

export const Starfield = React.forwardRef<StarfieldHandle, { className?: string }>(function Starfield(
  { className },
  ref,
) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const attractor = React.useRef<{ x: number; y: number } | null>(null);
  const attractStrength = React.useRef(0);
  const targetStrength = React.useRef(0);

  React.useImperativeHandle(ref, () => ({
    setAttractor: (p) => {
      if (p) attractor.current = p; // the last point is kept while the stars glide back home
      targetStrength.current = p ? 1 : 0;
    },
  }));

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0,
      height = 0,
      dpr = 1,
      stars: Star[] = [],
      frame = 0,
      last = performance.now(),
      nextComet = last + 4000 + Math.random() * 6000;
    const comets: Comet[] = [];
    const mouse = { x: 0, y: 0, sx: 0, sy: 0 }; // -1..1 from the centre, smoothed in sx/sy

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas!.width = Math.round(width * dpr);
      canvas!.height = Math.round(height * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      stars = makeStars(width, height);
      if (reduceMotion) draw(performance.now(), 0);
    }

    function onMove(e: PointerEvent) {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    }

    function drawSparkle(x: number, y: number, size: number) {
      ctx!.beginPath();
      ctx!.moveTo(x, y - size);
      ctx!.quadraticCurveTo(x, y, x + size, y);
      ctx!.quadraticCurveTo(x, y, x, y + size);
      ctx!.quadraticCurveTo(x, y, x - size, y);
      ctx!.quadraticCurveTo(x, y, x, y - size);
      ctx!.fill();
    }

    function draw(now: number, dt: number) {
      ctx!.clearRect(0, 0, width, height);
      const t = now / 1000;

      // smooth the parallax and the attraction strength (fast in, slow out)
      mouse.sx += (mouse.x - mouse.sx) * Math.min(1, dt * 3);
      mouse.sy += (mouse.y - mouse.sy) * Math.min(1, dt * 3);
      const goal = targetStrength.current;
      attractStrength.current += (goal - attractStrength.current) * Math.min(1, dt * (goal > attractStrength.current ? 3.5 : 0.9));
      const strength = attractStrength.current;
      const a = attractor.current;
      const rect = canvas!.getBoundingClientRect();
      const ax = a ? a.x - rect.left : 0,
        ay = a ? a.y - rect.top : 0;

      for (const s of stars) {
        const homeX = s.hx * width + Math.sin(t * 0.15 + s.drift) * 2.2 * s.z - mouse.sx * 16 * s.z;
        const homeY = s.hy * height + Math.cos(t * 0.12 + s.drift) * 2.2 * s.z - mouse.sy * 12 * s.z;

        // attraction towards the button: the closer the star, the further it travels
        let tx = 0,
          ty = 0,
          glow = 0;
        if (a && strength > 0.001) {
          const dx = ax - homeX,
            dy = ay - homeY,
            d = Math.hypot(dx, dy);
          if (d < ATTRACT_RADIUS) {
            const f = (1 - d / ATTRACT_RADIUS) ** 1.4 * strength;
            const pull = Math.min(0.42 * f, Math.max(0, (d - 40) / Math.max(d, 1)));
            tx = dx * pull;
            ty = dy * pull;
            glow = f;
          }
        }
        // ease towards the target: quick when drawn in, slow when going home
        const ease = Math.min(1, dt * (glow > 0.01 ? 4 : 1.2));
        s.x += (tx - s.x) * ease;
        s.y += (ty - s.y) * ease;

        const x = homeX + s.x,
          y = homeY + s.y;
        const twinkle = reduceMotion ? 0.8 : 0.55 + 0.45 * Math.sin(t * s.speed + s.phase);
        const alpha = Math.min(1, (0.4 + 0.6 * s.z) * twinkle + glow * 0.6);
        const radius = s.r * (1 + glow * 0.6);

        ctx!.globalAlpha = alpha;
        ctx!.fillStyle = s.color;
        if (s.sparkle) {
          ctx!.globalAlpha = alpha * 0.35;
          ctx!.beginPath();
          ctx!.arc(x, y, radius * 3.2, 0, Math.PI * 2);
          ctx!.fill();
          ctx!.globalAlpha = alpha;
          drawSparkle(x, y, radius * (2.6 + 0.8 * twinkle));
        } else {
          ctx!.beginPath();
          ctx!.arc(x, y, radius, 0, Math.PI * 2);
          ctx!.fill();
          if (glow > 0.15 || s.r > 1.5) {
            ctx!.globalAlpha = alpha * 0.18;
            ctx!.beginPath();
            ctx!.arc(x, y, radius * 3, 0, Math.PI * 2);
            ctx!.fill();
          }
        }
      }

      // a shooting star now and then
      if (!reduceMotion) {
        if (now > nextComet) {
          nextComet = now + 7000 + Math.random() * 9000;
          const fromLeft = Math.random() < 0.5;
          comets.push({
            x: fromLeft ? Math.random() * width * 0.5 : width * (0.5 + Math.random() * 0.5),
            y: Math.random() * height * 0.35,
            vx: (fromLeft ? 1 : -1) * (520 + Math.random() * 240),
            vy: 200 + Math.random() * 140,
            life: 1,
          });
        }
        for (let i = comets.length - 1; i >= 0; i--) {
          const c = comets[i];
          c.x += c.vx * dt;
          c.y += c.vy * dt;
          c.life -= dt * 0.9;
          if (c.life <= 0) {
            comets.splice(i, 1);
            continue;
          }
          const len = 0.16;
          const grad = ctx!.createLinearGradient(c.x, c.y, c.x - c.vx * len, c.y - c.vy * len);
          grad.addColorStop(0, `rgba(255, 236, 180, ${0.85 * c.life})`);
          grad.addColorStop(1, "rgba(255, 236, 180, 0)");
          ctx!.globalAlpha = 1;
          ctx!.strokeStyle = grad;
          ctx!.lineWidth = 1.6;
          ctx!.lineCap = "round";
          ctx!.beginPath();
          ctx!.moveTo(c.x, c.y);
          ctx!.lineTo(c.x - c.vx * len, c.y - c.vy * len);
          ctx!.stroke();
        }
      }
      ctx!.globalAlpha = 1;
    }

    function loop(now: number) {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      draw(now, dt);
      frame = requestAnimationFrame(loop);
    }

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    if (!reduceMotion) {
      window.addEventListener("pointermove", onMove, { passive: true });
      frame = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return <canvas ref={canvasRef} aria-hidden className={className} />;
});
