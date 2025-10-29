# Project Cosmos - Complete Architecture Documentation

## Overview
Project Cosmos is an AI-powered, on-demand "Expert Co-pilot" for software development teams. It acts as a centralized, learning knowledge base of previously solved crashes and bugs, accelerating debugging by providing immediate, context-aware historical information and concrete code suggestions.

## Core Architecture: The 2-Way On-Demand Model

The system follows a privacy-conscious, two-way architecture with clear separation of concerns:

```
Cursor IDE <--> Orion MCP Server <--> Nebula RAG Pipeline
```

### Key Design Principles
1. **Privacy-First**: Developer code is only transmitted when explicitly requested
2. **Lightweight**: Initial interactions send only metadata
3. **On-Demand**: Code snippets are requested only when necessary for analysis
4. **Centralized Knowledge**: Shared VectorDB for all historical resolutions
5. **Real-time**: Fast feedback loop between components

## Component Architecture

### 1. Cursor IDE (Developer Interface)
**Role**: Developer's primary interface and code editor
**Technology**: Cursor IDE with custom plugin
**Key Responsibilities**:
- Highlight code and error messages
- Send lightweight metadata-only requests initially
- Respond to Orion MCP requests for specific code snippets
- Display structured RCA and fix suggestions
- Maintain local code context

**Data Flow**:
- **Outbound**: Metadata (file, line range, error message, user context)
- **Inbound**: Code snippet requests, structured analysis results

### 2. Orion MCP (Mission Control Platform)
**Role**: Central orchestrator and sole gateway for IDE communication
**Technology**: Go-based server
**Key Responsibilities**:
- Receive and validate requests from Cursor
- Determine if code snippet is needed for analysis
- Request specific code snippets from Cursor when required
- Enrich requests with metadata (repo, branch, commit hash)
- Forward structured requests to Nebula RAG pipeline
- Return formatted results to Cursor
- Maintain lightweight caching of recent snippets
- Handle authentication and rate limiting

**Decision Logic**:
- Query Nebula with metadata first
- If confidence score is low or detailed analysis needed → request code snippet
- If high confidence with metadata alone → proceed without snippet

### 3. Nebula (RAG Pipeline)
**Role**: AI reasoning engine and knowledge processor
**Technology**: FastAPI-based service
**Key Responsibilities**:
- Receive enriched requests from Orion MCP
- Query VectorDB for similar historical resolutions
- Perform semantic similarity matching
- Combine code snippets with historical context
- Generate root cause analysis (RCA)
- Create actionable fix suggestions
- Generate code diffs and implementation guidance
- Calculate confidence scores

**AI Pipeline**:
1. **Retrieval**: Query VectorDB for similar past resolutions
2. **Augmentation**: Combine retrieved context with current code
3. **Generation**: Use LLM to generate RCA and fixes
4. **Validation**: Calculate confidence and relevance scores

### 4. Vector Database
**Role**: Centralized knowledge storage
**Technology**: Vector database (e.g., Pinecone, Weaviate, or Chroma)
**Key Responsibilities**:
- Store embeddings of historical bug resolutions
- Enable semantic similarity search
- Maintain structured fix documentation
- Support incremental learning and updates
- Provide fast retrieval for similar issues

## Detailed Data Flow

### Phase 1: Initial Query (Metadata Only)
```
Developer → Cursor → Orion MCP
```
**Payload**:
```json
{
  "repo": "payments-service",
  "file": "src/payments/handler.js",
  "line_range": "180-230",
  "error": "TypeError: Cannot read property 'id' of undefined",
  "user": "alice",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Phase 2: Orion MCP Decision & Code Request (If Needed)
```
Orion MCP → Cursor
```
**Request**:
```json
{
  "message": "Please send the code snippet for handler.js lines 180-230 for detailed root cause analysis.",
  "request_id": "req_12345",
  "priority": "high"
}
```

**Response**:
```json
{
  "code_snippet": "function handlePayment(req, res) {\n  const userId = req.user.id;\n  // ... rest of function\n}",
  "request_id": "req_12345",
  "metadata": {
    "total_lines": 50,
    "language": "javascript"
  }
}
```

### Phase 3: Enriched Analysis Request
```
Orion MCP → Nebula
```
**Payload**:
```json
{
  "error": "TypeError: Cannot read property 'id' of undefined",
  "code_snippet": "function handlePayment(req, res) {\n  const userId = req.user.id;\n  // ... rest of function\n}",
  "metadata": {
    "repo": "payments-service",
    "file": "src/payments/handler.js",
    "line_range": "180-230",
    "user": "alice",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "context": {
    "similar_issues_found": 3,
    "confidence_threshold": 0.7
  }
}
```

### Phase 4: RAG Processing
```
Nebula → VectorDB → LLM → Nebula
```
**VectorDB Query**: Find similar past resolutions
**LLM Processing**: Generate RCA and fixes
**Output**:
```json
{
  "root_cause": "Uninitialized user object before property access. The req.user is undefined when the function is called.",
  "related_tickets": ["PAY-451", "AUTH-123"],
  "fix_suggestion": "Add a guard clause to ensure req.user exists before accessing req.user.id",
  "code_diff": "--- old\n+++ new\n@@ -1,3 +1,5 @@\n function handlePayment(req, res) {\n+  if (!req.user) {\n+    return res.status(401).send('Unauthorized');\n+  }\n   const userId = req.user.id;",
  "confidence": 0.95,
  "similar_cases": [
    {
      "ticket": "PAY-451",
      "similarity": 0.89,
      "resolution": "Added user validation before property access"
    }
  ],
  "prevention_tips": [
    "Always validate request objects before property access",
    "Use middleware for authentication checks",
    "Implement proper error handling for undefined objects"
  ]
}
```

### Phase 5: Response Delivery
```
Nebula → Orion MCP → Cursor → Developer
```

## Security & Privacy Rules

### Data Handling Rules
1. **No Automatic Code Transmission**: Code is only sent when explicitly requested by Orion MCP
2. **Metadata-Only Initial Requests**: First interaction contains only file names, line ranges, and error messages
3. **Local Communication**: Cursor and Orion MCP communicate over localhost/IDE API
4. **Controlled Exposure**: Only specific code snippets are transmitted, not entire repositories
5. **User Consent**: Developers are informed when code snippets are requested

### Access Control
1. **User Authentication**: All requests include user context
2. **Repository Scoping**: Analysis is scoped to specific repositories
3. **Rate Limiting**: Orion MCP implements request throttling
4. **Audit Logging**: All requests and responses are logged for security

## Performance Optimizations

### Caching Strategy
1. **Orion MCP Level**: Cache recent code snippets to reduce redundant requests
2. **Nebula Level**: Cache similar query results for faster responses
3. **VectorDB Level**: Optimize embedding storage and retrieval

### Scalability Considerations
1. **Horizontal Scaling**: Multiple Orion MCP instances can connect to single Nebula
2. **Load Balancing**: Distribute requests across multiple Nebula instances
3. **Database Sharding**: Partition VectorDB by repository or team
4. **CDN Integration**: Cache static analysis results

## Error Handling & Resilience

### Error Scenarios
1. **Orion MCP Unavailable**: Cursor falls back to local analysis or shows error
2. **Nebula Timeout**: Orion MCP returns cached results or partial analysis
3. **VectorDB Issues**: Nebula uses fallback knowledge base
4. **Code Request Failure**: Orion MCP proceeds with metadata-only analysis

### Recovery Mechanisms
1. **Retry Logic**: Exponential backoff for failed requests
2. **Circuit Breaker**: Prevent cascade failures
3. **Graceful Degradation**: Provide partial results when possible
4. **Health Checks**: Monitor component availability

## Development Workflow Integration

### IDE Integration
1. **Seamless Triggering**: Error highlighting automatically triggers analysis
2. **Context Preservation**: Maintain cursor position and selection
3. **Non-blocking**: Analysis runs in background without blocking development
4. **Visual Feedback**: Clear indicators for analysis progress and results

### Team Collaboration
1. **Shared Knowledge**: All team members benefit from historical resolutions
2. **Learning System**: New fixes are automatically added to knowledge base
3. **Cross-Repository**: Learnings from one project can help with others
4. **Continuous Improvement**: System gets smarter with each resolved issue

## Monitoring & Analytics

### Key Metrics
1. **Response Times**: Orion MCP and Nebula processing times
2. **Success Rates**: Analysis accuracy and developer satisfaction
3. **Code Request Frequency**: How often snippets are needed
4. **Knowledge Base Growth**: New resolutions added over time
5. **Developer Adoption**: Usage patterns and feature utilization

### Observability
1. **Distributed Tracing**: Track requests across all components
2. **Performance Monitoring**: Real-time component health
3. **Error Tracking**: Comprehensive error logging and alerting
4. **Usage Analytics**: Understand developer behavior and needs

## Future Extensibility

### Planned Enhancements
1. **Multi-Language Support**: Beyond JavaScript to Python, Java, Go, etc.
2. **Advanced AI Models**: Integration with latest LLM capabilities
3. **Team-Specific Learning**: Custom knowledge bases per team
4. **Integration APIs**: Connect with Jira, GitHub, Slack, etc.
5. **Mobile Development**: Support for React Native, Flutter, etc.

### Architecture Flexibility
1. **Plugin System**: Easy addition of new analysis capabilities
2. **API Versioning**: Backward compatibility for evolving interfaces
3. **Microservices**: Potential to split components further
4. **Cloud Deployment**: Support for various cloud platforms

---

This architecture provides a robust, scalable, and privacy-conscious solution for AI-powered debugging assistance while maintaining developer productivity and code security.