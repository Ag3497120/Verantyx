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

// Greedy-generates up to max_tokens token ids continuing prompt_ptr/prompt_len,
// writing into out_ptr (capacity out_len). Returns the number of tokens
// actually written (>= 0), or a negative error code.
int32_t jcross_engine_generate(
    void *engine,
    const uint32_t *prompt_ptr, size_t prompt_len,
    size_t max_tokens,
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
