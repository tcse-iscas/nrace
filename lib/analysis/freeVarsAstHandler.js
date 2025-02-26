/*
 * Copyright (c) 2015 Samsung Electronics Co., Ltd.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *        http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
/// <reference path="../ts-declarations/node.d.ts" />
// initializes J$.configUtil
require('./configUtil');
function getFreeVars(ast) {
    var freeVarsTable = {};
    var na = J$.configUtil;
    var curVarNames = null;
    var freeVarsHandler = function (node, context) {
        var fv = na.freeVars(node);
        curVarNames = fv === na.ANY ? "ANY" : Object.keys(fv);
    };
    var visitorPost = {
        'CallExpression': function (node) {
            if (node.callee.object && node.callee.object.name === 'J$' && (node.callee.property.name === 'Fe')) {
                var iid = node.arguments[0].value;
                freeVarsTable[iid] = curVarNames;
            }
            return node;
        }
    };
    var visitorPre = {
        'FunctionExpression': freeVarsHandler,
        'FunctionDeclaration': freeVarsHandler
    };
    J$.astUtil.transformAst(ast, visitorPost, visitorPre);
    return freeVarsTable;
}
module.exports = getFreeVars;
//# sourceMappingURL=freeVarsAstHandler.js.map
