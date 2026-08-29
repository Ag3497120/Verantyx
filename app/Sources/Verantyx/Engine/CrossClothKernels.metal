#include <metal_stdlib>
using namespace metal;

// Optional XPBD-style foundation for cross-cloth.  These kernels intentionally
// use one writer per vertex and immutable input buffers.  They do not claim CPU
// parity, continuous collision, seam, bending, or production cloth fidelity.

struct CrossClothParticle {
    float4 positionAndInverseMass;
    float4 velocity;
};

struct CrossClothParameters {
    uint4 counts;     // vertex count, six-arm slot count, iteration, reserved
    float4 scalars;   // substep dt, velocity damping, relaxation, epsilon
    float4 gravity;
};

kernel void crossClothPredict(
    device const CrossClothParticle *oldParticles [[buffer(0)]],
    device float4 *predictedNext [[buffer(1)]],
    constant CrossClothParameters &parameters [[buffer(2)]],
    uint gid [[thread_position_in_grid]])
{
    if (gid >= parameters.counts.x) { return; }

    const CrossClothParticle old = oldParticles[gid];
    const float inverseMass = old.positionAndInverseMass.w;
    if (inverseMass == 0.0f) {
        predictedNext[gid] = old.positionAndInverseMass;
        return;
    }

    const float dt = parameters.scalars.x;
    const float3 velocity = old.velocity.xyz + parameters.gravity.xyz * dt;
    const float3 position = old.positionAndInverseMass.xyz + velocity * dt;
    predictedNext[gid] = float4(position, inverseMass);
}

kernel void crossClothProjectSixArm(
    device const float4 *projectionOld [[buffer(0)]],
    device float4 *projectionNext [[buffer(1)]],
    device const CrossClothParticle *massState [[buffer(2)]],
    device const int *neighbourIndices [[buffer(3)]],
    device const float *restLengths [[buffer(4)]],
    device const float *compliance [[buffer(5)]],
    constant CrossClothParameters &parameters [[buffer(6)]],
    uint gid [[thread_position_in_grid]])
{
    if (gid >= parameters.counts.x) { return; }

    const float4 oldValue = projectionOld[gid];
    const float inverseMass = massState[gid].positionAndInverseMass.w;
    if (inverseMass == 0.0f) {
        projectionNext[gid] = oldValue;
        return;
    }

    const uint slotCount = parameters.counts.y;
    const uint base = gid * slotCount;
    const float dt = parameters.scalars.x;
    const float epsilon = parameters.scalars.w;
    float3 correction = float3(0.0f);
    uint accepted = 0;

    // Fixed slot order (+X, -X, +Y, -Y, +Z, -Z) is part of the ABI.
    // All neighbours are read from projectionOld; no thread observes a value
    // written by this iteration.
    for (uint slot = 0; slot < slotCount; ++slot) {
        const uint constraint = base + slot;
        const int neighbour = neighbourIndices[constraint];
        if (neighbour < 0 || uint(neighbour) >= parameters.counts.x) { continue; }

        const float3 delta = oldValue.xyz - projectionOld[neighbour].xyz;
        const float length = metal::length(delta);
        if (!isfinite(length) || length <= epsilon) { continue; }

        const float rest = restLengths[constraint];
        const float alpha = compliance[constraint] / (dt * dt);
        const float neighbourMass = massState[neighbour].positionAndInverseMass.w;
        const float denominator = inverseMass + neighbourMass + alpha;
        if (!isfinite(denominator) || denominator <= epsilon) { continue; }

        const float constraintError = length - rest;
        const float lambda = -constraintError / denominator;
        correction += inverseMass * lambda * (delta / length);
        accepted += 1;
    }

    const float scale = accepted == 0 ? 0.0f : parameters.scalars.z / float(accepted);
    projectionNext[gid] = float4(oldValue.xyz + correction * scale, inverseMass);
}

kernel void crossClothFinalize(
    device const CrossClothParticle *oldParticles [[buffer(0)]],
    device const float4 *projectedOld [[buffer(1)]],
    device CrossClothParticle *particlesNext [[buffer(2)]],
    constant CrossClothParameters &parameters [[buffer(3)]],
    uint gid [[thread_position_in_grid]])
{
    if (gid >= parameters.counts.x) { return; }

    const CrossClothParticle old = oldParticles[gid];
    const float4 projected = projectedOld[gid];
    CrossClothParticle next;
    next.positionAndInverseMass = projected;
    if (old.positionAndInverseMass.w == 0.0f) {
        next.velocity = float4(0.0f);
    } else {
        const float3 velocity = (projected.xyz - old.positionAndInverseMass.xyz) /
            parameters.scalars.x;
        next.velocity = float4(velocity * parameters.scalars.y, 0.0f);
    }
    particlesNext[gid] = next;
}
