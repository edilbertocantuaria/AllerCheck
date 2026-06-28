# Faithfulness

## Faithfulness

The **Faithfulness** metric measures how factually consistent a `response` is with the `retrieved context`. It ranges from 0 to 1, with higher scores indicating better consistency.

A response is considered **faithful** if all its claims can be supported by the retrieved context.

To calculate this:
1. Identify all the claims in the response.
2. Check each claim to see if it can be inferred from the retrieved context.
3. Compute the faithfulness score using the formula:

$$
Faithfulness Score = Number of claims in the response supported by the retrieved context Total number of claims in the response
$$

### Example

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = Faithfulness(llm=llm)

# Evaluate
result = await scorer.ascore(
    user_input="When was the first super bowl?",
    response="The first superbowl was held on Jan 15, 1967",
    retrieved_contexts=[
        "The First AFL–NFL World Championship Game was an American football game played on January 15, 1967, at the Los Angeles Memorial Coliseum in Los Angeles."
    ]
)
print(f"Faithfulness Score: {result.value}")
```

Output:

```python
Faithfulness Score: 1.0
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    user_input="When was the first super bowl?",
    response="The first superbowl was held on Jan 15, 1967",
    retrieved_contexts=[...]
)
```

### How It’s Calculated

> **Example:** **Question**: Where and when was Einstein born?

**Context**: Albert Einstein (born 14 March 1879) was a German-born theoretical physicist, widely held to be one of the greatest and most influential scientists of all time

**High faithfulness answer**: Einstein was born in Germany on 14th March 1879.

**Low faithfulness answer**:  Einstein was born in Germany on 20th March 1879.

Let's examine how faithfulness was calculated using the low faithfulness answer:

- **Step 1:** Break the generated answer into individual statements.

- Statements:
- Statement 1: "Einstein was born in Germany."
- Statement 2: "Einstein was born on 20th March 1879."
- **Step 2:** For each of the generated statements, verify if it can be inferred from the given context.

- Statement 1: Yes
- Statement 2: No
- **Step 3:** Use the formula depicted above to calculate faithfulness.

$$
Faithfulness = 1 2 = 0.5
$$

## Legacy Metrics API

The following examples use the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above.

> **Deprecation Timeline:** This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the collections-based API shown above.

### Example with SingleTurnSample

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness

sample = SingleTurnSample(
        user_input="When was the first super bowl?",
        response="The first superbowl was held on Jan 15, 1967",
        retrieved_contexts=[
            "The First AFL–NFL World Championship Game was an American football game played on January 15, 1967, at the Los Angeles Memorial Coliseum in Los Angeles."
        ]
    )
scorer = Faithfulness(llm=evaluator_llm)
await scorer.single_turn_ascore(sample)
```

Output:

```python
1.0
```

### Faithfulness with HHEM-2.1-Open

Vectara's HHEM-2.1-Open is a classifier model (T5) that is trained to detect hallucinations from LLM generated text. This model can be used in the second step of calculating faithfulness, i.e. when claims are cross-checked with the given context to determine if it can be inferred from the context. The model is free, small, and open-source, making it very efficient in production use cases.

To use the model to calculate faithfulness:

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import FaithfulnesswithHHEM

sample = SingleTurnSample(
        user_input="When was the first super bowl?",
        response="The first superbowl was held on Jan 15, 1967",
        retrieved_contexts=[
            "The First AFL–NFL World Championship Game was an American football game played on January 15, 1967, at the Los Angeles Memorial Coliseum in Los Angeles."
        ]
    )
scorer = FaithfulnesswithHHEM(llm=evaluator_llm)
await scorer.single_turn_ascore(sample)
```

You can load the model onto a specified device by setting the `device` argument and adjust the batch size for inference using the `batch_size` parameter. By default, the model is loaded on the CPU with a batch size of 10:

```python
my_device = "cuda:0"
my_batch_size = 10

scorer = FaithfulnesswithHHEM(device=my_device, batch_size=my_batch_size)
await scorer.single_turn_ascore(sample)
```

---

# Context Precision

Context Precision is a metric that evaluates the retriever's ability to rank relevant chunks higher than irrelevant ones for a given query in the retrieved context. Specifically, it assesses the degree to which relevant chunks in the retrieved context are placed at the top of the ranking.

It is calculated as the mean of the precision@k for each chunk in the context. Precision@k is the ratio of the number of relevant chunks at rank k to the total number of chunks at rank k.

$$
Context Precision@K = ∑ k = 1 K ( Precision@k × v k ) Total number of relevant items in the top K results
$$

$$
Precision@k = true positives@k ( true positives@k + false positives@k )
$$

Where 

$$
K
$$

 is the total number of chunks in `retrieved_contexts` and 

$$
v k ∈ { 0 , 1 }
$$

 is the relevance indicator at rank 

$$
k
$$

.

## Examples

### Context Precision

The `ContextPrecision` metric evaluates whether retrieved contexts are useful for answering a question by comparing each context against a reference answer. Use this when you have a reference answer available.

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecision

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = ContextPrecision(llm=llm)

# Evaluate
result = await scorer.ascore(
    user_input="Where is the Eiffel Tower located?",
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=[
        "The Eiffel Tower is located in Paris.",
        "The Brandenburg Gate is located in Berlin."
    ]
)
print(f"Context Precision Score: {result.value}")
```

Output:

```python
Context Precision Score: 0.9999999999
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    user_input="Where is the Eiffel Tower located?",
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=[...]
)
```

### Context Utilization

The `ContextUtilization` metric evaluates whether retrieved contexts are useful by comparing each context against the generated response. Use this when you don't have a reference answer but have the response that was generated.

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextUtilization

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = ContextUtilization(llm=llm)

# Evaluate
result = await scorer.ascore(
    user_input="Where is the Eiffel Tower located?",
    response="The Eiffel Tower is located in Paris.",
    retrieved_contexts=[
        "The Eiffel Tower is located in Paris.",
        "The Brandenburg Gate is located in Berlin."
    ]
)
print(f"Context Utilization Score: {result.value}")
```

Output:

```python
Context Utilization Score: 0.9999999999
```

Note that even if an irrelevant chunk is present at the second position in the array, context precision remains the same. However, if this irrelevant chunk is placed at the first position, context precision reduces:

```python
result = await scorer.ascore(
    user_input="Where is the Eiffel Tower located?",
    response="The Eiffel Tower is located in Paris.",
    retrieved_contexts=[
        "The Brandenburg Gate is located in Berlin.",
        "The Eiffel Tower is located in Paris."
    ]
)
print(f"Context Utilization Score: {result.value}")
```

Output:

```python
Context Utilization Score: 0.49999999995
```

## Legacy Metrics API

The following examples use the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above.

> **Deprecation Timeline:** This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the collections-based API shown above.

### Example with SingleTurnSample

```python
from ragas import SingleTurnSample
from ragas.metrics import LLMContextPrecisionWithoutReference

context_precision = LLMContextPrecisionWithoutReference(llm=evaluator_llm)

sample = SingleTurnSample(
    user_input="Where is the Eiffel Tower located?",
    response="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."],
)

await context_precision.single_turn_ascore(sample)
```

Output:

```python
0.9999999999
```

### Context Precision without reference

The `LLMContextPrecisionWithoutReference` metric can be used without the availability of a reference answer. To estimate if the retrieved contexts are relevant, this method uses the LLM to compare each chunk in `retrieved_contexts` with the `response`.

#### Example

```python
from ragas import SingleTurnSample
from ragas.metrics import LLMContextPrecisionWithoutReference

context_precision = LLMContextPrecisionWithoutReference(llm=evaluator_llm)

sample = SingleTurnSample(
    user_input="Where is the Eiffel Tower located?",
    response="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."],
)

await context_precision.single_turn_ascore(sample)
```

Output:

```python
0.9999999999
```

### Context Precision with reference

The `LLMContextPrecisionWithReference` metric can be used when you have both retrieved contexts and also a reference response associated with a `user_input`. To estimate if the retrieved contexts are relevant, this method uses the LLM to compare each chunk in `retrieved_contexts` with the `reference`.

#### Example

```python
from ragas import SingleTurnSample
from ragas.metrics import LLMContextPrecisionWithReference

context_precision = LLMContextPrecisionWithReference(llm=evaluator_llm)

sample = SingleTurnSample(
    user_input="Where is the Eiffel Tower located?",
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."],
)

await context_precision.single_turn_ascore(sample)
```

Output:

```python
0.9999999999
```

## Non LLM Based Context Precision

This metric uses non-LLM-based methods (such as Levenshtein distance measure) to determine whether a retrieved context is relevant.

### Context Precision with reference contexts

The `NonLLMContextPrecisionWithReference` metric is designed for scenarios where both retrieved contexts and reference contexts are available for a `user_input`. To determine if a retrieved context is relevant, this method compares each retrieved context or chunk in `retrieved_contexts` with every context in `reference_contexts` using a non-LLM-based similarity measure.

Note that this metric would need the rapidfuzz package to be installed: `pip install rapidfuzz`.

#### Example

```python
from ragas import SingleTurnSample
from ragas.metrics import NonLLMContextPrecisionWithReference

context_precision = NonLLMContextPrecisionWithReference()

sample = SingleTurnSample(
    retrieved_contexts=["The Eiffel Tower is located in Paris."],
    reference_contexts=["Paris is the capital of France.", "The Eiffel Tower is one of the most famous landmarks in Paris."]
)

await context_precision.single_turn_ascore(sample)
```

Output:

```python
0.9999999999
```

## ID Based Context Precision

IDBasedContextPrecision provides a direct and efficient way to measure precision by comparing the IDs of retrieved contexts with reference context IDs. This metric is particularly useful when you have a unique ID system for your documents and want to evaluate retrieval performance without comparing the actual content.

The metric computes precision using retrieved_context_ids and reference_context_ids, with values ranging between 0 and 1. Higher values indicate better performance. It works with both string and integer IDs.

The formula for calculating ID-based context precision is as follows:

$$
ID-Based Context Precision = Number of retrieved context IDs found in reference context IDs Total number of retrieved context IDs
$$

### Example

```python
from ragas import SingleTurnSample
from ragas.metrics import IDBasedContextPrecision

sample = SingleTurnSample(
    retrieved_context_ids=["doc_1", "doc_2", "doc_3", "doc_4"],
    reference_context_ids=["doc_1", "doc_4", "doc_5", "doc_6"]
)

id_precision = IDBasedContextPrecision()
await id_precision.single_turn_ascore(sample)
```

Output:

```python
0.5
```

In this example, out of the 4 retrieved context IDs, only 2 ("doc_1" and "doc_4") are found in the reference context IDs, resulting in a precision score of 0.5 or 50%.

---

# Context Recall

Context Recall measures how many of the relevant documents (or pieces of information) were successfully retrieved. It focuses on not missing important results. Higher recall means fewer relevant documents were left out. In short, recall is about not missing anything important.

Since it is about not missing anything, calculating context recall always requires a reference to compare against. The LLM-based Context Recall metric uses `reference` as a proxy to `reference_contexts`, which makes it easier to use as annotating reference contexts can be very time-consuming. To estimate context recall from the `reference`, the reference is broken down into claims, and each claim is analyzed to determine whether it can be attributed to the retrieved context or not. In an ideal scenario, all claims in the reference answer should be attributable to the retrieved context.

The formula for calculating context recall is as follows:

$$
Context Recall = Number of claims in the reference supported by the retrieved context Total number of claims in the reference
$$

## Example

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextRecall

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = ContextRecall(llm=llm)

# Evaluate
result = await scorer.ascore(
    user_input="Where is the Eiffel Tower located?",
    retrieved_contexts=["Paris is the capital of France."],
    reference="The Eiffel Tower is located in Paris."
)
print(f"Context Recall Score: {result.value}")
```

Output:

```python
Context Recall Score: 1.0
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    user_input="Where is the Eiffel Tower located?",
    retrieved_contexts=["Paris is the capital of France."],
    reference="The Eiffel Tower is located in Paris."
)
```

## LLM Based Context Recall (Legacy API)

> **Legacy API:** The following example uses the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above. This API will be deprecated in version 0.4 and removed in version 1.0.

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import LLMContextRecall

sample = SingleTurnSample(
    user_input="Where is the Eiffel Tower located?",
    response="The Eiffel Tower is located in Paris.",
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["Paris is the capital of France."],
)

context_recall = LLMContextRecall(llm=evaluator_llm)
await context_recall.single_turn_ascore(sample)
```

Output:

```python
1.0
```

## Non LLM Based Context Recall

`NonLLMContextRecall` metric is computed using `retrieved_contexts` and `reference_contexts`, and the values range between 0 and 1, with higher values indicating better performance. This metrics uses non-LLM string comparison metrics to identify if a retrieved context is relevant or not. You can use any non LLM based metrics as distance measure to identify if a retrieved context is relevant or not.

The formula for calculating context recall is as follows:

$$
context recall = | Number of relevant contexts retrieved | | Total number of reference contexts |
$$

### Example

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import NonLLMContextRecall

sample = SingleTurnSample(
    retrieved_contexts=["Paris is the capital of France."],
    reference_contexts=["Paris is the capital of France.", "The Eiffel Tower is one of the most famous landmarks in Paris."]
)

context_recall = NonLLMContextRecall()
await context_recall.single_turn_ascore(sample)
```

Output

```python
0.5
```

## ID BasedContext Recall

ID Based Context Recall
IDBasedContextRecall provides a direct and efficient way to measure recall by comparing the IDs of retrieved contexts with reference context IDs. This metric is particularly useful when you have a unique ID system for your documents and want to evaluate retrieval performance without comparing the actual content.

The metric computes recall using retrieved_context_ids and reference_context_ids, with values ranging between 0 and 1. Higher values indicate better performance. It works with both string and integer IDs.

The formula for calculating ID-based context recall is as follows:

$$
ID-Based Context Recall = Number of reference context IDs found in retrieved context IDs Total number of reference context IDs
$$

### Example

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import IDBasedContextRecall

sample = SingleTurnSample(
    retrieved_context_ids=["doc_1", "doc_2", "doc_3"], 
    reference_context_ids=["doc_1", "doc_4", "doc_5", "doc_6"]
)

id_recall = IDBasedContextRecall()
await id_recall.single_turn_ascore(sample)
```

Output

```python
0.25
```

---

# Context Entities Recall

## Context Entities Recall

`ContextEntityRecall` metric gives the measure of recall of the retrieved context, based on the number of entities present in both `reference` and `retrieved_contexts` relative to the number of entities present in the `reference` alone. Simply put, it is a measure of what fraction of entities is recalled from `reference`. This metric is useful in fact-based use cases like tourism help desk, historical QA, etc. This metric can help evaluate the retrieval mechanism for entities, based on comparison with entities present in `reference`, because in cases where entities matter, we need the `retrieved_contexts` which cover them.

To compute this metric, we use two sets:

- **$$
R E
$$**: The set of entities in the reference.
- **$$
R C E
$$**: The set of entities in the retrieved contexts.

We calculate the number of entities common to both sets (

$$
R C E ∩ R E
$$

) and divide it by the total number of entities in the reference (

$$
R E
$$

). The formula is:

$$
Context Entity Recall = Number of common entities between R C E and R E Total number of entities in R E
$$

### Example

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextEntityRecall

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = ContextEntityRecall(llm=llm)

# Evaluate
result = await scorer.ascore(
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."]
)
print(f"Context Entity Recall Score: {result.value}")
```

Output:

```python
Context Entity Recall Score: 0.999999995
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."]
)
```

### How It’s Calculated

> **Example:** **reference**: The Taj Mahal is an ivory-white marble mausoleum on the right bank of the river Yamuna in the Indian city of Agra. It was commissioned in 1631 by the Mughal emperor Shah Jahan to house the tomb of his favorite wife, Mumtaz Mahal.
**High entity recall context**: The Taj Mahal is a symbol of love and architectural marvel located in Agra, India. It was built by the Mughal emperor Shah Jahan in memory of his beloved wife, Mumtaz Mahal. The structure is renowned for its intricate marble work and beautiful gardens surrounding it.
**Low entity recall context**: The Taj Mahal is an iconic monument in India. It is a UNESCO World Heritage Site and attracts millions of visitors annually. The intricate carvings and stunning architecture make it a must-visit destination.

Let us consider the reference and the retrieved contexts given above.

- **Step-1**: Find entities present in the reference.
- Entities in ground truth (RE) - ['Taj Mahal', 'Yamuna', 'Agra', '1631', 'Shah Jahan', 'Mumtaz Mahal']
- **Step-2**: Find entities present in the retrieved contexts.
- Entities in context (RCE1) - ['Taj Mahal', 'Agra', 'Shah Jahan', 'Mumtaz Mahal', 'India']
- Entities in context (RCE2) - ['Taj Mahal', 'UNESCO', 'India']
- **Step-3**: Use the formula given above to calculate entity-recall

$$
context entity recall 1 = | R C E 1 ∩ R E | | R E | = 4 / 6 = 0.666
$$

$$
context entity recall 2 = | R C E 2 ∩ R E | | R E | = 1 / 6
$$

We can see that the first context had a high entity recall, because it has a better entity coverage given the reference. If these two retrieved contexts were fetched by two retrieval mechanisms on same set of documents, we could say that the first mechanism was better than the other in use-cases where entities are of importance.

## Legacy Metrics API

The following examples use the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above.

> **Deprecation Timeline:** This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the collections-based API shown above.

### Example with SingleTurnSample

```python
from ragas import SingleTurnSample
from ragas.metrics import ContextEntityRecall

sample = SingleTurnSample(
    reference="The Eiffel Tower is located in Paris.",
    retrieved_contexts=["The Eiffel Tower is located in Paris."],
)

scorer = ContextEntityRecall(llm=evaluator_llm)

await scorer.single_turn_ascore(sample)
```

Output:

```python
0.999999995
```

---

# Noise Sensitivity

`NoiseSensitivity` measures how often a system makes errors by providing incorrect responses when utilizing either relevant or irrelevant retrieved documents. The score ranges from 0 to 1, with lower values indicating better performance. Noise sensitivity is computed using the `user_input`, `reference`, `response`, and the `retrieved_contexts`.

To estimate noise sensitivity, each claim in the generated response is examined to determine whether it is correct based on the ground truth and whether it can be attributed to the relevant (or irrelevant) retrieved context. Ideally, all claims in the answer should be supported by the relevant retrieved context.

$$
noise sensitivity (relevant) = | Total number of incorrect claims in response | | Total number of claims in the response |
$$

### Example

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import NoiseSensitivity

# Setup LLM
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)

# Create metric
scorer = NoiseSensitivity(llm=llm)

# Evaluate
result = await scorer.ascore(
    user_input="What is the Life Insurance Corporation of India (LIC) known for?",
    response="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, known for its vast portfolio of investments. LIC contributes to the financial stability of the country.",
    reference="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.",
    retrieved_contexts=[
        "The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.",
        "LIC is the largest insurance company in India, with a vast network of policyholders and huge investments.",
        "As the largest institutional investor in India, LIC manages substantial funds, contributing to the financial stability of the country.",
        "The Indian economy is one of the fastest-growing major economies in the world, thanks to sectors like finance, technology, manufacturing etc."
    ]
)
print(f"Noise Sensitivity Score: {result.value}")
```

Output:

```python
Noise Sensitivity Score: 0.3333333333333333
```

To calculate noise sensitivity of irrelevant context, you can set the `mode` parameter to `irrelevant`:

```python
scorer = NoiseSensitivity(llm=llm, mode="irrelevant")
result = await scorer.ascore(
    user_input="What is the Life Insurance Corporation of India (LIC) known for?",
    response="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, known for its vast portfolio of investments. LIC contributes to the financial stability of the country.",
    reference="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.",
    retrieved_contexts=[
        "The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.",
        "LIC is the largest insurance company in India, with a vast network of policyholders and huge investments.",
        "As the largest institutional investor in India, LIC manages substantial funds, contributing to the financial stability of the country.",
        "The Indian economy is one of the fastest-growing major economies in the world, thanks to sectors like finance, technology, manufacturing etc."
    ]
)
print(f"Noise Sensitivity (Irrelevant) Score: {result.value}")
```

Output:

```python
Noise Sensitivity (Irrelevant) Score: 0.0
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    user_input="What is the Life Insurance Corporation of India (LIC) known for?",
    response="The Life Insurance Corporation of India (LIC) is the largest insurance company in India...",
    reference="The Life Insurance Corporation of India (LIC) is the largest insurance company...",
    retrieved_contexts=[...]
)
```

## How It’s Calculated

> **Example:** Question: What is the Life Insurance Corporation of India (LIC) known for?

Ground truth: The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.

Relevant Retrieval:
    - The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.
    - LIC is the largest insurance company in India, with a vast network of policyholders and a significant role in the financial sector.
    - As the largest institutional investor in India, LIC manages a substantial life fund, contributing to the financial stability of the country.

Irrelevant Retrieval:
    - The Indian economy is one of the fastest-growing major economies in the world, thanks to the sectors like finance, technology, manufacturing etc.

Let's examine how noise sensitivity in relevant context was calculated:

- **Step 1:** Identify the relevant contexts from which the ground truth can be inferred.

- Ground Truth:
The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.
- Contexts:

- Context 1: The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.
- Context 2: LIC is the largest insurance company in India, with a vast network of policyholders and a significant role in the financial sector.
- Context 3: As the largest institutional investor in India, LIC manages a substantial funds`, contributing to the financial stability of the country.
- **Step 2:** Verify if the claims in the generated answer can be inferred from the relevant context.

- Answer:
The Life Insurance Corporation of India (LIC) is the largest insurance company in India, known for its vast portfolio of investments. LIC contributes to the financial stability of the country.
- Contexts:

- Context 1: The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.
- Context 2: LIC is the largest insurance company in India, with a vast network of policyholders and a significant role in the financial sector.
- Context 3: As the largest institutional investor in India, LIC manages a substantial funds, contributing to the financial stability of the country.
- **Step 3:** Identify any incorrect claims in the answer (i.e., answer statements that are not supported by the ground truth).

- Ground Truth:
The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.
- Answer:
The Life Insurance Corporation of India (LIC) is the largest insurance company in India, known for its vast portfolio of investments. LIC contributes to the financial stability of the country.

Explanation: The ground truth does not mention anything about LIC contributing to the financial stability of the country. Therefore, this statement in the answer is incorrect.

Incorrect Statement: 1
Total claims: 3
- **Step 4:** Calculate noise sensitivity using the formula:

$$
noise sensitivity = 1 3 = 0.333
$$

This results in a noise sensitivity score of 0.333, indicating that one out of three claims in the answer was incorrect.

## Legacy Metrics API

The following examples use the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above.

> **Deprecation Timeline:** This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the collections-based API shown above.

### Example with SingleTurnSample

```python
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import NoiseSensitivity

sample = SingleTurnSample(
    user_input="What is the Life Insurance Corporation of India (LIC) known for?",
    response="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, known for its vast portfolio of investments. LIC contributes to the financial stability of the country.",
    reference="The Life Insurance Corporation of India (LIC) is the largest insurance company in India, established in 1956 through the nationalization of the insurance industry. It is known for managing a large portfolio of investments.",
    retrieved_contexts=[
        "The Life Insurance Corporation of India (LIC) was established in 1956 following the nationalization of the insurance industry in India.",
        "LIC is the largest insurance company in India, with a vast network of policyholders and huge investments.",
        "As the largest institutional investor in India, LIC manages substantial funds, contributing to the financial stability of the country.",
        "The Indian economy is one of the fastest-growing major economies in the world, thanks to sectors like finance, technology, manufacturing etc."
    ]
)

scorer = NoiseSensitivity(llm=evaluator_llm)
await scorer.single_turn_ascore(sample)
```

Output:

```python
0.3333333333333333
```

To calculate noise sensitivity of irrelevant context, you can set the `mode` parameter to `irrelevant`:

```python
scorer = NoiseSensitivity(mode="irrelevant")
await scorer.single_turn_ascore(sample)
```

Credits: Noise sensitivity was introduced in RAGChecker

---

# Response Relevancy

## Answer Relevancy

The **Answer Relevancy** metric measures how relevant a response is to the user input. It ranges from 0 to 1, with higher scores indicating better alignment with the user input.

An answer is considered relevant if it directly and appropriately addresses the original question. This metric focuses on how well the answer matches the intent of the question, without evaluating factual accuracy. It penalizes answers that are incomplete or include unnecessary details.

This metric is calculated using the `user_input` and the `response` as follows:

1. Generate a set of artificial questions (default is 3) based on the response. These questions are designed to reflect the content of the response.
2. Compute the cosine similarity between the embedding of the user input (

$$
E o
$$

) and the embedding of each generated question (

$$
E g i
$$

).
3. Take the average of these cosine similarity scores to get the **Answer Relevancy**:

$$
Answer Relevancy = 1 N ∑ i = 1 N cosine similarity ( E g i , E o )
$$

$$
Answer Relevancy = 1 N ∑ i = 1 N E g i ⋅ E o ‖ E g i ‖ ‖ E o ‖
$$

Where:

- 

$$
E g i
$$

: Embedding of the 

$$
i t h
$$

 generated question.

- 

$$
E o
$$

: Embedding of the user input.

- 

$$
N
$$

: Number of generated questions (default is 3, configurable via `strictness` parameter).

**Note**: While the score usually falls between 0 and 1, it is not guaranteed due to cosine similarity's mathematical range of -1 to 1.

### Example

```python
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from ragas.metrics.collections import AnswerRelevancy

# Setup LLM and embeddings
client = AsyncOpenAI()
llm = llm_factory("gpt-4o-mini", client=client)
embeddings = embedding_factory("openai", model="text-embedding-3-small", client=client)

# Create metric
scorer = AnswerRelevancy(llm=llm, embeddings=embeddings)

# Evaluate
result = await scorer.ascore(
    user_input="When was the first super bowl?",
    response="The first superbowl was held on Jan 15, 1967"
)
print(f"Answer Relevancy Score: {result.value}")
```

Output:

```python
Answer Relevancy Score: 0.9165088378587264
```

> **Synchronous Usage:** If you prefer synchronous code, you can use the `.score()` method instead of `.ascore()`:

```python
result = scorer.score(
    user_input="When was the first super bowl?",
    response="The first superbowl was held on Jan 15, 1967"
)
```

### How It’s Calculated

> **Example:** Question: Where is France and what is it's capital?

Low relevance answer: France is in western Europe.

High relevance answer: France is in western Europe and Paris is its capital.

To calculate the relevance of the answer to the given question, we follow two steps:

- **Step 1:** Reverse-engineer 'n' variants of the question from the generated answer using a Large Language Model (LLM). 
  For instance, for the first answer, the LLM might generate the following possible questions:

- *Question 1:* "In which part of Europe is France located?"
- *Question 2:* "What is the geographical location of France within Europe?"
- *Question 3:* "Can you identify the region of Europe where France is situated?"
- **Step 2:** Calculate the mean cosine similarity between the generated questions and the actual question.

The underlying concept is that if the answer correctly addresses the question, it is highly probable that the original question can be reconstructed solely from the answer.

## Legacy Metrics API

The following examples use the legacy metrics API pattern. For new projects, we recommend using the collections-based API shown above.

> **Deprecation Timeline:** This API will be deprecated in version 0.4 and removed in version 1.0. Please migrate to the collections-based API shown above.

### Example with SingleTurnSample

```python
from ragas import SingleTurnSample 
from ragas.metrics import ResponseRelevancy

sample = SingleTurnSample(
        user_input="When was the first super bowl?",
        response="The first superbowl was held on Jan 15, 1967",
        retrieved_contexts=[
            "The First AFL–NFL World Championship Game was an American football game played on January 15, 1967, at the Los Angeles Memorial Coliseum in Los Angeles."
        ]
    )

scorer = ResponseRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings)
await scorer.single_turn_ascore(sample)
```

Output:

```python
0.9165088378587264
```