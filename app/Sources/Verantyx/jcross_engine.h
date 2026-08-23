#ifndef JCROSS_ENGINE_H
#define JCROSS_ENGINE_H

// C ABI mirror of the extern "C" functions exported by the jcross_engine_glm
// Rust crate (libjcross_engine_glm.dylib), source of truth:
// /Users/motonishikoudai/Projects/verantyx-cli/jcross_engine_glm/src/lib.rs
// (~lines 2837-3269). Parameter order/types cross-checked against the
// ctypes.argtypes declarations in verantyx_mind.py's RustBrain class.
//
// All functions take an opaque `void *` engine handle returned by
// jcross_engine_create. None of these are safe to call from multiple
// threads concurrently on the same handle (the Rust side uses interior
// mutability with no locking) -- serialize calls per engine instance.

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Loads a .jgen model file and returns an opaque engine handle, or NULL on
// failure (bad path, load error -- check stderr for the Rust-side message).
void *jcross_engine_create(const char *path);

// Frees the engine and all cached weights/KV-cache. `engine` must not be
// used after this call.
void jcross_engine_destroy(void *engine);

// Clears the KV-cache so the engine can be reused for a fresh generation.
// Call before each independent generate/encode sequence that should not
// see a prior turn's cached state.
void jcross_engine_reset(void *engine);

// Releases composed weight caches (CPU f32 + GPU) and the KV-cache, dropping
// RAM back to ~mmap only. Weights recompose lazily on next use.
void jcross_engine_trim(void *engine);

// Returns the model's hidden dimension (>0), or a negative value on error.
int32_t jcross_engine_hidden_dim(void *engine);

// Returns the number of transformer layers.
int32_t jcross_engine_num_layers(void *engine);

// Wrap system+question in THIS MODEL'S turn markers, taken from its sidecar.
// Returns bytes written, -1 bad pointer, -2 buffer too small, -3 the
// converter did not recognise this model's markers. -3 is an answer: the
// caller must supply the format rather than fall back to ChatML, which is
// right for Qwen and silently wrong for both gemma families.
int32_t jcross_engine_chat_wrap(void *engine, const char *system,
                                const char *user, char *out, int32_t out_cap);

// Whole-conversation variant. turns_json is
// [{"role":"user","content":"…"}, …]. Same return codes.
int32_t jcross_engine_chat_wrap_json(void *engine, const char *turns_json,
                                     char *out, int32_t out_cap);

// "gemma4" | "gemma" | "chatml" | "" when unknown.
int32_t jcross_engine_chat_family(void *engine, char *out, int32_t out_cap);

// Greedy-generates up to max_tokens token ids continuing prompt_ptr/prompt_len,
// writing into out_ptr (capacity out_len). Returns the number of tokens
// actually written (>= 0), or a negative error code.
int32_t jcross_engine_generate(
    void *engine,
    const uint32_t *prompt_ptr, size_t prompt_len,
    size_t max_tokens,
    uint32_t *out_ptr, size_t out_len
);

// Called synchronously, on the calling thread, immediately after each token
// is decided during jcross_engine_generate_streaming -- same generation
// (same code path, same KV-cache reuse) as jcross_engine_generate, just with
// a per-token observation point. Return 0 to stop generation early
// (cooperative cancellation); any other value continues.
typedef int32_t (*JCrossTokenCallback)(void *ctx, uint32_t token);

// Streaming variant of jcross_engine_generate: identical generation, but
// invokes `callback(ctx, token)` after each token. out_ptr/out_len still
// receive the full generated sequence at the end. Returns the number of
// tokens actually written (>= 0), or a negative error code -- same
// contract as jcross_engine_generate.
int32_t jcross_engine_generate_streaming(
    void *engine,
    const uint32_t *prompt_ptr, size_t prompt_len,
    size_t max_tokens,
    JCrossTokenCallback callback, void *ctx,
    uint32_t *out_ptr, size_t out_len
);

// Forwards tokens_ptr/tokens_len through the full model and writes the
// final-token, post-final-norm hidden state (length == hidden_dim) into
// out_ptr. Returns 0 on success, negative on error.
int32_t jcross_engine_encode(
    void *engine,
    const uint32_t *tokens_ptr, size_t tokens_len,
    float *out_ptr, size_t out_len
);

// Same as jcross_engine_encode, but prepends n_soft embedding-space vectors
// (soft_ptr, row-major n_soft x hidden) as virtual tokens before tokens_ptr.
// This is the "vector communication" / encode_soft injection path.
int32_t jcross_engine_encode_soft(
    void *engine,
    const float *soft_ptr, size_t n_soft, size_t hidden,
    const uint32_t *tokens_ptr, size_t tokens_len,
    float *out_ptr, size_t out_len
);

// Dumps the last-token hidden state after each of n_layers requested layer
// indices (layers_ptr). A layer index equal to num_layers means
// post-final-norm. out_ptr must hold n_layers * hidden_dim floats,
// row-major in the same order as layers_ptr.
int32_t jcross_engine_encode_layers(
    void *engine,
    const uint32_t *tokens_ptr, size_t tokens_len,
    const uint32_t *layers_ptr, size_t n_layers,
    float *out_ptr, size_t out_len
);

// Generation with memory supplied as vectors rather than as prompt text.
//
// Two independent routes, both optional, usable together:
//   soft_ptr    n_soft * hidden_dim f32, prepended as virtual tokens before the
//               prompt (embedding space -- these occupy real positions)
//   inject_*    n_inject (layer, hidden_dim vector, alpha) triples, blended into
//               that layer's residual during prefill (norm-matched, so alpha is
//               a mix ratio and not an amount added)
//
// inject_each_step != 0 re-applies the layer blend on every decode step instead
// of conditioning once during prefill.
//
// Measured on qwen2.5-0.5b: alpha up to ~0.4 keeps generation coherent; 0.5 and
// above degrades, and 1.0 collapses to a repeated token. alpha=1 means "replace
// the residual with this direction", so that is correct behaviour rather than a
// defect -- but it does mean the useful band is narrow.
//
// Returns the number of tokens written, or a negative error code.
int32_t jcross_engine_generate_injected(
    void *engine,
    const uint32_t *prompt_ptr, size_t prompt_len,
    const float *soft_ptr, size_t n_soft,
    const uint32_t *inject_layers_ptr,
    const float *inject_vecs_ptr,
    const float *inject_alphas_ptr,
    size_t n_inject,
    int32_t inject_each_step,
    // 0 = blend the last prompt position only (execute_inject_at_layer's
    // convention, measured inert for generation); 1 = blend every prompt
    // position, which is the variant that actually steers.
    int32_t blend_all_positions,
    size_t max_tokens,
    uint32_t *out_ptr, size_t out_len
);

// ---------------------------------------------------------------------------
// Layer-range execution (pipeline parallelism across two machines)
// ---------------------------------------------------------------------------
//
// Runs layers [start_layer, end_layer) only. Two entry points differing solely
// in what the range starts from: token ids for a head segment, a caller-supplied
// residual for anything downstream of one. Every other forward path in this
// engine begins at token embeddings and ends at the final norm, which is why a
// split model needs these.
//
// flags:
//   1  FINAL_NORM      apply the model's final RMSNorm after end_layer
//   2  LM_HEAD_ARGMAX  project the last row through lm_head, greedy-argmax, and
//                      write the token id to out_token_ptr (implies FINAL_NORM;
//                      out_ptr/out_len are then unused)
//   4  LAST_TOKEN_ONLY return only the final row of the hidden state
//
// out_ptr must hold (rows * hidden_dim) floats, row-major, where rows is
// seq_len unless LAST_TOKEN_ONLY is set.
//
// Returns 0 on success; -1 bad args, -2 engine error, -3 out_len/shape
// mismatch, -4 layer range invalid for this model, -5 architecture unsupported
// (gemma4 -- its per-layer embeddings cannot be rebuilt from a mid-stack
// residual, so it is refused rather than silently approximated).
int32_t jcross_engine_segment_from_tokens(
    void *engine,
    const uint32_t *tokens_ptr, size_t tokens_len,
    uint32_t start_layer, uint32_t end_layer,
    size_t start_pos, uint32_t flags,
    float *out_ptr, size_t out_len,
    uint32_t *out_token_ptr
);

// Same, but fed by a [seq_len, hidden_dim] residual (row-major f32) produced by
// an earlier segment -- possibly on another machine.
int32_t jcross_engine_segment_from_hidden(
    void *engine,
    const float *hidden_ptr, size_t seq_len,
    uint32_t start_layer, uint32_t end_layer,
    size_t start_pos, uint32_t flags,
    float *out_ptr, size_t out_len,
    uint32_t *out_token_ptr
);

// Blends inject_ptr (length inject_len == hidden_dim) into the residual
// stream immediately before inject_layer, continues the forward pass to
// the final norm, and writes the resulting last-token hidden state into
// out_ptr. alpha=1.0 replaces the residual at that point; alpha=0.0 is a
// no-op (pure passthrough). This is the "surgical" hidden-state
// intervention path, as opposed to encode_soft's input-side injection.
int32_t jcross_engine_inject_at_layer(
    void *engine,
    const uint32_t *tokens_ptr, size_t tokens_len,
    uint32_t inject_layer,
    const float *inject_ptr, size_t inject_len,
    float alpha,
    float *out_ptr, size_t out_len
);

// Milestone P: blends MULTIPLE (layer, vector, alpha) injections into ONE
// forward pass, and snapshots the residual at each requested observe
// layer. n_inject may be 0 (pass NULL for inject_layers_ptr/inject_vecs_ptr/
// alphas_ptr in that case) to just observe without injecting. Semantics:
// inject_layers use inject_at_layer's PRE-layer blend convention; observe_
// layers use encode_layers's POST-layer snapshot convention (they are not
// the same "layer 0" -- see the Rust doc comment on
// execute_inject_multi_layer for why). out_ptr must hold
// n_observe * hidden_dim floats, row-major, same order as observe_layers_ptr.
// soft_ptr is (n_soft x hidden, row-major) and prepends soft tokens. It was
// missing from this signature while the Rust side always accepted it, which
// left the soft-prefix route unreachable through this call.
int32_t jcross_engine_inject_multi_layer(
    void *engine,
    const uint32_t *tokens_ptr, size_t tokens_len,
    const float *soft_ptr, size_t n_soft,
    const uint32_t *inject_layers_ptr, const float *inject_vecs_ptr, const float *alphas_ptr, size_t n_inject,
    const uint32_t *observe_layers_ptr, size_t n_observe,
    float *out_ptr, size_t out_len
);

// SVD-projects input_ptr (length input_len) through the named layer's
// low-rank factors. Not used by Milestones A-C; declared for completeness.
int32_t jcross_engine_project(
    void *engine,
    const char *layer_name,
    const float *input_ptr, size_t input_len,
    float *out_ptr, size_t out_len
);

// "Telepathic resonance" -- iteratively projects a thought vector toward
// the token manifold via the named layer (lm_head-style). Not used by
// Milestones A-C; declared for completeness.
int32_t jcross_engine_resynthesize(
    void *engine,
    const char *layer_name,
    const float *input_ptr, size_t input_len,
    float temperature,
    float *out_ptr, size_t out_len
);

// "Entropy lock" -- projects input_ptr through the named layer and returns
// both the single most-likely token (out_token) and the distribution's
// entropy (out_entropy, lower = more confident). Use this to gate whether
// a vector (e.g. one refined by optimize_thought_in_place) is confident
// enough to decode into text, without needing a full generate pass.
int32_t jcross_engine_puzzle_inference(
    void *engine,
    const char *layer_name,
    const float *input_ptr, size_t input_len,
    uint32_t *out_token, float *out_entropy
);

// "Latent gradient descent" -- iteratively refines input_ptr IN PLACE
// (up to max_steps steps at learning rate lr) to minimize entropy at the
// named layer, i.e. optimizes a vector directly in embedding space toward
// a more confident "thought" rather than sampling tokens one at a time.
// Returns the final entropy in out_entropy. input_ptr is mutated.
int32_t jcross_engine_optimize_thought_in_place(
    void *engine,
    const char *layer_name,
    float *input_ptr, size_t input_len,
    size_t max_steps, float lr, float temperature,
    float *out_entropy
);

// Full top-K vocabulary distribution (softmax over the named layer's
// logits), for callers that need more than the argmax -- Council's
// divergence-packet claims, dissent-key extraction, and soft-sequence
// construction all operate on multiple candidates, not just the top-1
// token. Caller allocates out_token_ids/out_probs with capacity k;
// out_count receives how many entries were actually written (<= k).
int32_t jcross_engine_topk_distribution(
    void *engine,
    const char *layer_name,
    const float *input_ptr, size_t input_len,
    size_t k,
    uint32_t *out_token_ids, float *out_probs,
    size_t *out_count
);

// A single token's raw input-embedding row (length == hidden_dim), for
// soft-token sequence construction (dist_to_soft_sequence-style callers
// need arbitrary candidate tokens' embedding rows, not a forward pass).
int32_t jcross_engine_embedding_row(
    void *engine,
    uint32_t token_id,
    float *out_ptr, size_t out_len
);

#ifdef __cplusplus
}
#endif

#endif // JCROSS_ENGINE_H
