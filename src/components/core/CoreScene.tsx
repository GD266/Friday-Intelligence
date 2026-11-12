import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import type { FridayMood } from '@/types';
import { CoreOrb } from './CoreOrb';

export interface CoreSceneProps {
  mood: FridayMood;
  audioLevel: number;
  className?: string;
}

interface MoodPalette {
  primary: number;
  secondary: number;
  accent: number;
  speed: number;
}

const PALETTES: Record<FridayMood, MoodPalette> = {
  idle: { primary: 0x38d9ff, secondary: 0x8b5cf6, accent: 0x77e8ff, speed: 0.55 },
  listening: { primary: 0x3ff5d0, secondary: 0x38a8ff, accent: 0xc6fff3, speed: 1.15 },
  thinking: { primary: 0xffb347, secondary: 0xff5ea8, accent: 0xffe0a3, speed: 1.8 },
  speaking: { primary: 0xa78bfa, secondary: 0x38d9ff, accent: 0xf0e9ff, speed: 1.45 },
  alert: { primary: 0xff5e6c, secondary: 0xffb347, accent: 0xffd6d9, speed: 1.9 },
};

const CORE_VERTEX = `
  uniform float uTime;
  uniform float uAudio;
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  varying float vWave;

  void main() {
    vec3 p = position;
    float n = sin(p.x * 4.2 + uTime * 1.35)
            * cos(p.y * 5.1 - uTime * 1.05)
            * sin(p.z * 4.7 + uTime * 0.9);
    float ridge = sin((p.x + p.y + p.z) * 8.0 - uTime * 2.2);
    float displacement = n * (0.045 + uAudio * 0.2) + ridge * (0.008 + uAudio * 0.035);
    p += normal * displacement;
    vWave = n;

    vNormal = normalize(normalMatrix * normal);
    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    vViewPosition = -mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const CORE_FRAGMENT = `
  uniform float uTime;
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uAccent;
  uniform float uAudio;
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  varying float vWave;

  void main() {
    vec3 normal = normalize(vNormal);
    vec3 viewDir = normalize(vViewPosition);
    float facing = max(dot(normal, viewDir), 0.0);
    float fresnel = pow(1.0 - facing, 2.2);

    float bands = 0.5 + 0.5 * sin(vWave * 7.0 + uTime * 2.4 + normal.y * 3.4);
    float scan = smoothstep(0.94, 1.0, sin(uTime * 3.1 + normal.y * 26.0) * 0.5 + 0.5);
    float heartbeat = 0.9 + 0.1 * sin(uTime * 2.1);

    vec3 color = mix(uColorA, uColorB, clamp(bands * 0.75 + fresnel * 0.4, 0.0, 1.0));
    color += uAccent * (fresnel * 1.45 + scan * 0.35 + uAudio * 0.5);
    color *= heartbeat;

    gl_FragColor = vec4(color, 0.82 + fresnel * 0.18);
  }
`;

function createGlowTexture(): THREE.Texture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const context = canvas.getContext('2d');
  if (context) {
    const gradient = context.createRadialGradient(128, 128, 0, 128, 128, 128);
    gradient.addColorStop(0, 'rgba(190, 250, 255, 0.9)');
    gradient.addColorStop(0.18, 'rgba(100, 225, 255, 0.45)');
    gradient.addColorStop(0.48, 'rgba(110, 130, 255, 0.12)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, 256, 256);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export const CoreScene = ({ mood, audioLevel, className }: CoreSceneProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const moodRef = useRef(mood);
  const audioRef = useRef(audioLevel);
  const [failed, setFailed] = useState(false);

  moodRef.current = mood;
  audioRef.current = audioLevel;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance',
      });
    } catch {
      setFailed(true);
      return;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.setAttribute('aria-hidden', 'true');
    renderer.domElement.style.position = 'absolute';
    renderer.domElement.style.inset = '0';
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.style.pointerEvents = 'none';
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0.15, 7.6);

    const root = new THREE.Group();
    scene.add(root);

    const currentPrimary = new THREE.Color(PALETTES.idle.primary);
    const currentSecondary = new THREE.Color(PALETTES.idle.secondary);
    const currentAccent = new THREE.Color(PALETTES.idle.accent);
    const targetPrimary = new THREE.Color(PALETTES.idle.primary);
    const targetSecondary = new THREE.Color(PALETTES.idle.secondary);
    const targetAccent = new THREE.Color(PALETTES.idle.accent);

    // ------------------------------------------------------------------
    // Volumetric halo and central shader sphere
    // ------------------------------------------------------------------
    const glowTexture = createGlowTexture();
    const haloMaterial = new THREE.SpriteMaterial({
      map: glowTexture,
      color: 0x6fe6ff,
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const halo = new THREE.Sprite(haloMaterial);
    halo.scale.setScalar(6.8);
    root.add(halo);

    const coreUniforms = {
      uTime: { value: 0 },
      uAudio: { value: 0 },
      uColorA: { value: new THREE.Color(PALETTES.idle.primary) },
      uColorB: { value: new THREE.Color(PALETTES.idle.secondary) },
      uAccent: { value: new THREE.Color(PALETTES.idle.accent) },
    };

    const coreGeometry = new THREE.IcosahedronGeometry(1.25, 48);
    const coreMaterial = new THREE.ShaderMaterial({
      vertexShader: CORE_VERTEX,
      fragmentShader: CORE_FRAGMENT,
      uniforms: coreUniforms,
      transparent: true,
      depthWrite: false,
    });
    const core = new THREE.Mesh(coreGeometry, coreMaterial);
    root.add(core);

    const innerCore = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.36, 4),
      new THREE.MeshBasicMaterial({
        color: 0xe8feff,
        transparent: true,
        opacity: 0.92,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
    );
    root.add(innerCore);

    const wireShell = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1.58, 3),
      new THREE.MeshBasicMaterial({
        color: 0x8cefff,
        wireframe: true,
        transparent: true,
        opacity: 0.07,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
    );
    root.add(wireShell);

    // ------------------------------------------------------------------
    // Gyroscopic rings and telemetry ticks
    // ------------------------------------------------------------------
    const ringGroup = new THREE.Group();
    root.add(ringGroup);

    const ringDefinitions = [
      { radius: 1.9, tube: 0.007, color: 0x66e7ff, opacity: 0.55, tilt: [1.12, 0.2, 0.1], speed: 0.42 },
      { radius: 2.12, tube: 0.006, color: 0xa78bfa, opacity: 0.45, tilt: [-0.72, 0.9, 0.4], speed: -0.3 },
      { radius: 2.34, tube: 0.005, color: 0xff7fb7, opacity: 0.28, tilt: [0.35, -1.1, 0.72], speed: 0.2 },
    ] as const;

    const rings = ringDefinitions.map((definition) => {
      const material = new THREE.MeshBasicMaterial({
        color: definition.color,
        transparent: true,
        opacity: definition.opacity,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(
        new THREE.TorusGeometry(definition.radius, definition.tube, 8, 220),
        material
      );
      mesh.rotation.set(definition.tilt[0], definition.tilt[1], definition.tilt[2]);
      ringGroup.add(mesh);
      return { mesh, material, speed: definition.speed, baseOpacity: definition.opacity };
    });

    const tickGeometry = new THREE.BoxGeometry(0.012, 0.055, 0.012);
    const tickMaterial = new THREE.MeshBasicMaterial({
      color: 0x85e9ff,
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const tickCount = 84;
    const ticks = new THREE.InstancedMesh(tickGeometry, tickMaterial, tickCount);
    const tickDummy = new THREE.Object3D();
    for (let index = 0; index < tickCount; index += 1) {
      const angle = (index / tickCount) * Math.PI * 2;
      const major = index % 6 === 0;
      tickDummy.position.set(Math.cos(angle) * 2.72, Math.sin(angle) * 2.72, 0);
      tickDummy.rotation.set(0, 0, angle + Math.PI / 2);
      tickDummy.scale.set(major ? 1.8 : 1, major ? 1.7 : 0.75, 1);
      tickDummy.updateMatrix();
      ticks.setMatrixAt(index, tickDummy.matrix);
    }
    ticks.instanceMatrix.needsUpdate = true;
    const tickGroup = new THREE.Group();
    tickGroup.rotation.set(0.55, -0.35, 0.12);
    tickGroup.add(ticks);
    ringGroup.add(tickGroup);

    // ------------------------------------------------------------------
    // Orbiting shards and moons
    // ------------------------------------------------------------------
    const shardCount = 34;
    const shardMesh = new THREE.InstancedMesh(
      new THREE.TetrahedronGeometry(0.052, 0),
      new THREE.MeshBasicMaterial({
        color: 0x9cefff,
        transparent: true,
        opacity: 0.6,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
      shardCount
    );
    const shards = Array.from({ length: shardCount }, (_, index) => ({
      radius: 2.1 + (index % 7) * 0.18,
      speed: 0.16 + (index % 5) * 0.035,
      phase: (index / shardCount) * Math.PI * 2,
      tilt: (index % 3) * 0.55 - 0.55,
      spin: 0.4 + (index % 4) * 0.2,
      scale: 0.7 + (index % 5) * 0.14,
    }));
    const shardDummy = new THREE.Object3D();
    root.add(shardMesh);

    const moons = [
      { radius: 2.32, speed: 0.32, phase: 0.4, tilt: 0.3, color: 0xb9fbff, size: 0.055 },
      { radius: 2.55, speed: -0.22, phase: 2.3, tilt: -0.5, color: 0xc7b6ff, size: 0.042 },
      { radius: 2.05, speed: 0.4, phase: 4.4, tilt: 0.85, color: 0xffb9d6, size: 0.036 },
    ] as const;
    const moonMeshes = moons.map((moon) => {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(moon.size, 12, 12),
        new THREE.MeshBasicMaterial({ color: moon.color })
      );
      root.add(mesh);
      return mesh;
    });

    // ------------------------------------------------------------------
    // Energy filaments + expanding pulse rings
    // ------------------------------------------------------------------
    const filamentGroup = new THREE.Group();
    root.add(filamentGroup);
    for (let index = 0; index < 7; index += 1) {
      const points: THREE.Vector3[] = [];
      for (let step = 0; step < 5; step += 1) {
        const angle = (step / 4) * Math.PI * 2 + index * 0.7;
        const radius = 1.36 + Math.sin(index * 2.1 + step * 1.7) * 0.32;
        points.push(
          new THREE.Vector3(
            Math.cos(angle) * radius,
            Math.sin(angle * 1.3 + index) * 0.75,
            Math.sin(angle) * radius * 0.6
          )
        );
      }
      const curve = new THREE.CatmullRomCurve3(points);
      const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(46));
      const material = new THREE.LineBasicMaterial({
        color: index % 2 === 0 ? 0x7fe8ff : 0xb69dff,
        transparent: true,
        opacity: 0.16,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const line = new THREE.Line(geometry, material);
      line.userData.spin = 0.12 + index * 0.025;
      line.userData.phase = index;
      filamentGroup.add(line);
    }

    const pulseRings = Array.from({ length: 3 }, (_, index) => {
      const material = new THREE.MeshBasicMaterial({
        color: index === 0 ? 0x66e7ff : index === 1 ? 0x9b7bff : 0xff8ac4,
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const mesh = new THREE.Mesh(new THREE.TorusGeometry(1.45, 0.005, 6, 160), material);
      mesh.rotation.set(0.9 + index * 0.3, 0.2 + index * 0.4, 0.3);
      root.add(mesh);
      return { mesh, material, offset: index / 3 };
    });

    // ------------------------------------------------------------------
    // Particle vortex
    // ------------------------------------------------------------------
    const particleCount = 1350;
    const particlePositions = new Float32Array(particleCount * 3);
    const particleColors = new Float32Array(particleCount * 3);
    const cool = new THREE.Color(0x4ddcff);
    const warm = new THREE.Color(0xa98bff);
    for (let index = 0; index < particleCount; index += 1) {
      const radius = 1.75 + Math.random() * 3.4;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const flatten = 0.35 + Math.random() * 0.65;
      particlePositions[index * 3] = radius * Math.sin(phi) * Math.cos(theta);
      particlePositions[index * 3 + 1] = radius * Math.cos(phi) * flatten;
      particlePositions[index * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
      const mix = Math.random();
      const color = cool.clone().lerp(warm, mix);
      particleColors[index * 3] = color.r;
      particleColors[index * 3 + 1] = color.g;
      particleColors[index * 3 + 2] = color.b;
    }
    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    particleGeometry.setAttribute('color', new THREE.BufferAttribute(particleColors, 3));
    const particleMaterial = new THREE.PointsMaterial({
      size: 0.024,
      vertexColors: true,
      transparent: true,
      opacity: 0.78,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const particles = new THREE.Points(particleGeometry, particleMaterial);
    root.add(particles);

    // ------------------------------------------------------------------
    // Interaction, sizing, animation
    // ------------------------------------------------------------------
    const pointer = { x: 0, y: 0 };
    const onPointerMove = (event: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = ((event.clientY - rect.top) / rect.height) * 2 - 1;
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    const resize = () => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };

    const observer =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    observer?.observe(container);
    window.addEventListener('resize', resize);
    resize();

    const clock = new THREE.Clock();
    let frame = 0;
    let disposed = false;

    const animate = () => {
      if (disposed) return;
      frame = window.requestAnimationFrame(animate);
      if (document.hidden) return;

      const dt = Math.min(0.05, clock.getDelta());
      const time = clock.elapsedTime;

      const palette = PALETTES[moodRef.current];
      targetPrimary.setHex(palette.primary);
      targetSecondary.setHex(palette.secondary);
      targetAccent.setHex(palette.accent);
      currentPrimary.lerp(targetPrimary, 0.035);
      currentSecondary.lerp(targetSecondary, 0.035);
      currentAccent.lerp(targetAccent, 0.035);

      const audio = Math.min(1, Math.max(0, audioRef.current));
      const energy = Math.min(1, audio * 0.8 + (moodRef.current === 'thinking' ? 0.25 : 0));
      const speed = palette.speed;

      coreUniforms.uTime.value = time;
      coreUniforms.uAudio.value += (audio - coreUniforms.uAudio.value) * 0.1;
      coreUniforms.uColorA.value.copy(currentPrimary);
      coreUniforms.uColorB.value.copy(currentSecondary);
      coreUniforms.uAccent.value.copy(currentAccent);

      core.rotation.y += dt * 0.16 * speed;
      core.rotation.x = Math.sin(time * 0.22) * 0.16;
      core.scale.setScalar(1 + audio * 0.07 + Math.sin(time * 1.7) * 0.012);
      innerCore.rotation.y -= dt * 0.8;
      innerCore.rotation.x += dt * 0.4;
      innerCore.scale.setScalar(0.85 + audio * 0.5 + Math.sin(time * 2.6) * 0.08);
      (innerCore.material as THREE.MeshBasicMaterial).color.copy(currentAccent);

      wireShell.rotation.y -= dt * 0.09 * speed;
      wireShell.rotation.z += dt * 0.035;
      (wireShell.material as THREE.MeshBasicMaterial).color.copy(currentPrimary);

      ringGroup.rotation.y += dt * 0.06 * speed;
      ringGroup.rotation.x += dt * 0.018 * speed;
      for (const ring of rings) {
        ring.mesh.rotation.z += dt * 0.09 * ring.speed * speed;
        ring.material.color.copy(ring.speed > 0 ? currentPrimary : currentSecondary);
        ring.material.opacity = ring.baseOpacity * (0.7 + energy * 0.5);
      }
      tickGroup.rotation.z -= dt * 0.07 * speed;
      tickMaterial.opacity = 0.4 + energy * 0.35;

      for (let index = 0; index < shardCount; index += 1) {
        const shard = shards[index];
        const angle = time * shard.speed * speed + shard.phase;
        shardDummy.position.set(
          Math.cos(angle) * shard.radius,
          Math.sin(angle * 1.4 + shard.phase) * shard.radius * shard.tilt,
          Math.sin(angle) * shard.radius
        );
        shardDummy.rotation.set(time * shard.spin, angle, time * shard.spin * 0.6);
        shardDummy.scale.setScalar(shard.scale);
        shardDummy.updateMatrix();
        shardMesh.setMatrixAt(index, shardDummy.matrix);
      }
      shardMesh.instanceMatrix.needsUpdate = true;
      (shardMesh.material as THREE.MeshBasicMaterial).color.copy(currentAccent);
      (shardMesh.material as THREE.MeshBasicMaterial).opacity = 0.42 + energy * 0.35;

      moonMeshes.forEach((mesh, index) => {
        const moon = moons[index];
        const angle = time * moon.speed * speed + moon.phase;
        mesh.position.set(
          Math.cos(angle) * moon.radius,
          Math.sin(angle * 1.3) * moon.radius * moon.tilt,
          Math.sin(angle) * moon.radius
        );
        mesh.scale.setScalar(1 + Math.sin(time * 3 + index) * 0.16 + audio * 0.25);
      });

      filamentGroup.children.forEach((child, index) => {
        const line = child as THREE.Line;
        line.rotation.y = time * (line.userData.spin as number) * speed + index;
        line.rotation.x = Math.sin(time * 0.3 + index) * 0.4;
        const material = line.material as THREE.LineBasicMaterial;
        material.opacity = 0.1 + energy * 0.12 + Math.sin(time * 1.4 + index) * 0.04;
      });

      pulseRings.forEach((pulse) => {
        const phase = (time * (0.16 + energy * 0.25) + pulse.offset) % 1;
        pulse.mesh.scale.setScalar(1 + phase * 1.55);
        pulse.material.opacity = Math.max(0, (1 - phase) * (0.12 + energy * 0.3));
        pulse.mesh.rotation.z += dt * 0.12;
      });

      particles.rotation.y += dt * 0.028 * speed;
      particles.rotation.x = Math.sin(time * 0.12) * 0.1;
      particleMaterial.opacity = 0.55 + energy * 0.32;

      haloMaterial.opacity = 0.42 + energy * 0.24 + Math.sin(time * 1.2) * 0.04;
      haloMaterial.color.copy(currentPrimary);

      root.rotation.y += (pointer.x * 0.32 + Math.sin(time * 0.16) * 0.05 - root.rotation.y) * 0.035;
      root.rotation.x += (pointer.y * 0.2 - root.rotation.x) * 0.035;

      camera.position.x = Math.sin(time * 0.17) * 0.18;
      camera.position.y = 0.15 + Math.cos(time * 0.2) * 0.1;
      camera.lookAt(0, 0, 0);

      renderer.render(scene, camera);
    };

    if (reducedMotion) {
      // Render one composed frame. No continuous motion.
      const palette = PALETTES[moodRef.current];
      coreUniforms.uColorA.value.setHex(palette.primary);
      coreUniforms.uColorB.value.setHex(palette.secondary);
      coreUniforms.uAccent.value.setHex(palette.accent);
      haloMaterial.color.setHex(palette.primary);
      renderer.render(scene, camera);
    } else {
      animate();
    }

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointerMove);
      handleContextLoss();
      renderer.dispose();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };

    function handleContextLoss() {
      const geometrySet = new Set<THREE.BufferGeometry>();
      const materialSet = new Set<THREE.Material>();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (mesh.geometry) geometrySet.add(mesh.geometry);
        const material = mesh.material;
        if (Array.isArray(material)) {
          material.forEach((entry) => materialSet.add(entry));
        } else if (material) {
          materialSet.add(material);
        }
      });
      geometrySet.forEach((geometry) => geometry.dispose());
      materialSet.forEach((material) => material.dispose());
      glowTexture.dispose();
      renderer.forceContextLoss();
    }
  }, []);

  if (failed) {
    return <CoreOrb mood={mood} size="hero" audioLevel={audioLevel} />;
  }

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'relative', width: '100%', height: '100%' }}
    />
  );
};

CoreScene.displayName = 'CoreScene';

export default CoreScene;
